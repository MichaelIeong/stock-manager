#!/usr/bin/env python3
"""持倉盈虧計算 — 讀取 CNBC 報價 JSON，計算完整組合 P&L；含美股 24 小時參考報價。

用法：
    python3 scripts/quotes.py [json_file]

若未指定檔案，自動找 DATA/ 下最新 quotes_*.json。

輸出：每檔持倉的現價、成本、市值、盈虧、組合總覽。
      美股未開盤（盤前/盤後/休市）時，主表「現價」自動採用盤前/盤後 CNBC
      即時價或 Cboe 24 小時夜間參考價（非前一晚常規收盤價），並於「來源」列標註；
      美股常規交易時段才顯示常規收盤（即時成交）價。
"""

import json
import re
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deficit import (  # noqa: E402
    TOTAL_DEFICIT, HALF_TARGET, FLOOR_TARGET,
    BASELINE_DATE, BASELINE_INCOME, MONTHS_LEFT, net_recovery,
)
from pathlib import Path

# ── 持倉成本（與 positions.md 同步，更新持倉時同步修改此處） ──

US_POSITIONS = {}  # 模板預設值（空白）— 請填入你自己的資料

HK_POSITIONS = {}  # 模板預設值（空白）— 請填入你自己的資料

CN_POSITIONS = {}  # 模板預設值（空白）— 請填入你自己的資料

# ── 標的名稱（中文）── 分析報表除代碼外附名稱，提升可讀性。
# ⚠️ 新增標的時必須同步此處；US 代碼較直觀可加可不加，但 A 股/港股必須有。
SYMBOL_NAMES = {}  # 模板預設值（空白）— 請填入你自己的資料

# 現金倉
CASH_HKD = 0.0  # 模板預設值

# ── 已實現獲利（已平倉部位；與 positions.md 同步） ──
# 備兌 Call 權利金（如有）：填寫你的 covered Call 資料（張數／履約價／到期日）
CALL_PREMIUM_GROSS_HKD = 0.0  # 模板預設值
CALL_FEE_HKD = 0.0  # 模板預設值
CALL_PREMIUM_HKD = None  # 模板預設值

REALIZED_GAINS = []  # 模板預設值（空白）— 請填入你自己的資料


def norm_hk(symbol: str) -> str:
    """港股代碼正規化：去掉 .HK 前的多餘前導零，令 CNBC 回傳的
    '02800.HK' 與腳本鍵值 '2800.HK' 能正確匹配（避免靜默漏算）。"""
    s = (symbol or "").upper()
    if s.endswith(".HK"):
        code = s[:-3].lstrip("0") or "0"
        return code + ".HK"
    return s


def sym_name(sym: str) -> str:
    """返回標的中文名稱；自動正規化港股代碼前導零。"""
    return SYMBOL_NAMES.get(norm_hk(sym), "")


def fetch_fx():
    """從 open.er-api.com 拉取最新匯率，回傳 (usd_hkd, hkd_cny)。"""
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        rates = data.get("rates", {})
        usd_hkd = rates.get("HKD")
        usd_cny = rates.get("CNY")
        hkd_cny = usd_cny / usd_hkd if (usd_hkd and usd_cny) else None
        if usd_hkd and hkd_cny:
            return usd_hkd, hkd_cny
    except Exception:
        pass
    # 備用（手動更新）
    return 7.844, 0.8606


def fetch_cboe(symbol: str):
    """Cboe 延時報價（免 key）：夜間 20:00–04:00 ET 仍更新，延遲約 15 分鐘。

    回傳 {"price","bid","ask","ts"} 或 None。沙箱時鐘偏離會令 SSL 驗證失敗，
    故用 curl --insecure。
    """
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/quotes/{symbol}.json"
    try:
        r = subprocess.run(
            ["curl", "-sS", "--insecure", "-m", "15", "-A",
             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
             "-H", "Accept: application/json", url],
            capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
        d = json.loads(r.stdout)
        dd = d.get("data") or {}
        if dd.get("current_price") is None:
            return None
        return {
            "price": float(dd["current_price"]),
            "bid": dd.get("bid"),
            "ask": dd.get("ask"),
            "ts": d.get("timestamp", ""),  # 美東時間
        }
    except Exception:
        return None


def find_latest_quotes(data_dir: str = "DATA") -> str:
    """找 DATA/ 下最新的 quotes JSON 檔（只認 quotes_YYYY-MM-DD.json 格式）。"""
    import re
    p = Path(data_dir)
    pattern = re.compile(r"^quotes_\d{4}-\d{2}-\d{2}\.json$")
    files = sorted(f for f in p.glob("quotes_*.json") if pattern.match(f.name))
    if not files:
        print("錯誤：找不到任何 quotes_YYYY-MM-DD.json")
        sys.exit(1)
    return str(files[-1])


def load_quotes(path: str) -> dict:
    """讀取 CNBC JSON，回傳 {symbol: {last, change_pct, status, time, ...}}。"""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"錯誤：找不到報價檔 {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"錯誤：報價檔 JSON 解析失敗（{path}）：{e}")
        sys.exit(1)

    quotes = []
    # CNBC 結構: FormattedQuoteResult.FormattedQuote[]
    if "FormattedQuoteResult" in data:
        quotes = data["FormattedQuoteResult"].get("FormattedQuote", [])
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and "symbol" in v[0]:
                quotes = v
                break
    if isinstance(quotes, dict):  # 防禦：單一回傳時可能是 dict 而非 list
        quotes = [quotes]

    result = {}
    for q in quotes:
        if not isinstance(q, dict) or "symbol" not in q:
            continue
        raw_last = q.get("last")
        try:
            last = float(raw_last) if raw_last is not None else None
        except (ValueError, TypeError):
            last = None

        result[norm_hk(q["symbol"])] = {
            "last": last,
            "change": q.get("change"),
            "change_pct": q.get("change_pct"),
            "previous_close": q.get("previous_day_closing"),
            "status": q.get("curmktstatus", "N/A"),
            "currency": q.get("currencyCode", "N/A"),
            "time": q.get("last_timedate", ""),
            "name": q.get("name") or q.get("shortName") or q["symbol"],
            # ExtendedMktQuote：盤前/盤後價（PRE_MKT/POST_MKT）；深夜為 POST_MKT_PREV 舊數據
            "ext_type": (q.get("ExtendedMktQuote") or {}).get("type", ""),
            "ext_last": (q.get("ExtendedMktQuote") or {}).get("last"),
            "ext_pct": (q.get("ExtendedMktQuote") or {}).get("change_pct", ""),
            "ext_time": (q.get("ExtendedMktQuote") or {}).get("last_timedate", ""),
        }
    return result


def us_live_price(sym: str, q: dict, usd_hkd: float):
    """美股現價：未開盤時取盤前/盤後 CNBC 即時價，否則取 Cboe 24h 夜間參考價；
    美股常規交易時段（REG_MKT）用常規收盤價 `last`（即時成交價）。
    回傳 (price:float|None, src:str)。

    ⚠️ 已知 CNBC 怪象：REG_MKT 時 `ExtendedMktQuote` 可能仍殘留過時的
    PRE_MKT/POST_MKT 舊價（ext_last）。必須優先用 `last`，勿被舊 ext 覆蓋。
    """
    status = q.get("status", "")
    ext_type = q.get("ext_type", "")
    last = q.get("last")
    # 常規交易時段：直接用收盤價（即時成交價），忽略殘留的舊 ext 價
    if status == "REG_MKT":
        if last is not None:
            return last, "收盤"
        # last 缺失才續走 ext / Cboe 回退
    # 盤前/盤後成交價（CNBC ExtendedMktQuote）
    if ext_type in ("PRE_MKT", "POST_MKT") and q.get("ext_last") is not None:
        try:
            p = float(q["ext_last"])
            label = "盤前 CNBC" if ext_type == "PRE_MKT" else "盤後 CNBC"
            return p, label
        except (ValueError, TypeError):
            pass
    # 其餘時段（盤前/盤後無成交、深夜休市）：Cboe 24h 參考
    cboe = fetch_cboe(sym)
    if cboe:
        return cboe["price"], "Cboe 夜間"
    # 回退
    return last, "收盤"


def parse_quote_time(s: str):
    """從 CNBC 的 last_timedate（如 '4:08 PM CTT' / '11:44 AM EDT'）解析出
    24 小時制 (hour, minute)，無法解析回傳 None。"""
    m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", s or "", re.IGNORECASE)
    if not m:
        return None
    h = int(m.group(1)); mm = int(m.group(2)); ap = m.group(3).upper()
    if ap == "PM" and h != 12:
        h += 12
    elif ap == "AM" and h == 12:
        h = 0
    return h, mm


def session_for(market: str, q: dict) -> str:
    """回傳該市場目前所屬交易時段的中文標籤（精確到連續/競價/盤前後/休市）。"""
    status = q.get("status", "")
    ext = q.get("ext_type", "")
    t = parse_quote_time(q.get("time", ""))
    if market == "US":
        # 常規時段優先：忽略 CNBC 殘留的舊 PRE/POST ext 標記
        if status == "REG_MKT":
            return "常規交易時段（即時成交價）"
        if ext == "PRE_MKT":
            return "盤前時段（盤前 CNBC 即時價）"
        if ext == "POST_MKT":
            return "盤後時段（盤後 CNBC 即時價）"
        return "休市（Cboe 24h 夜間參考價，非成交價）"
    # 港股 / A 股：依本地時間精確標示連續交易與收市/收盤競價
    if status != "REG_MKT":
        return "休市"
    if t is None:
        return "常規交易時段"
    mint = t[0] * 60 + t[1]
    if market == "HK":
        if 570 <= mint < 720:
            return "上午連續交易時段（即時成交價）"
        if 780 <= mint < 960:
            return "下午連續交易時段（即時成交價）"
        if 960 <= mint <= 970:
            return "收市競價時段（收市價）"
        return "常規交易時段"
    if market == "CN":
        if 570 <= mint < 690:
            return "上午連續交易時段（即時成交價）"
        if 780 <= mint < 897:
            return "下午連續交易時段（即時成交價）"
        if 897 <= mint <= 900:
            return "收盤競價時段（收盤價）"
        return "常規交易時段"
    return "常規交易時段"


def section_note(quotes: dict, symbols, market: str) -> str:
    """產生該市場的報價時點 + 交易時段註記（取第一檔有報價的標的）。"""
    for s in symbols:
        q = quotes.get(norm_hk(s))
        if q and q.get("last") is not None:
            sess = session_for(market, q)
            return f"報價時點：{q.get('time', '')} ｜ {sess}"
    return ""


def pnl_pct(cost, current):
    return ((current - cost) / cost) * 100 if cost else 0


def main():
    # 找報價檔
    if len(sys.argv) > 1:
        json_path = sys.argv[1]
    else:
        json_path = find_latest_quotes()

    print(f"📊 報價來源: {json_path}")

    # 拉取實時匯率
    usd_hkd, hkd_cny = fetch_fx()
    cny_hkd = 1 / hkd_cny  # 1 CNY = ? HKD
    print(f"💱 匯率: USD/HKD={usd_hkd:.4f}  HKD/CNY={hkd_cny:.4f}  CNY/HKD={cny_hkd:.4f}")
    print()

    quotes = load_quotes(json_path)

    # ── 美股 ──
    # 今日盈虧日界：UTC+8 04:00（＝美東 16:00 收盤，即美股昨收更新點）
    print("━" * 99)
    print("🇺🇸 美股持倉（今日盈虧日界：UTC+8 04:00 = 美東收盤）")
    note = section_note(quotes, US_POSITIONS, "US")
    if note:
        print(note)
    print("━" * 99)
    print(f"{'代碼':<8}{'名稱':<9} {'市':<3} {'股數':>4} {'成本':>9} {'現價':>9} {'來源':<10}{'市值':>11} {'持倉盈虧':>12}{'今日盈虧':>12} {'%':>7}")
    print("-" * 99)

    us_total_cost = 0.0
    us_total_value = 0.0
    us_total_day = 0.0
    for sym, pos in US_POSITIONS.items():
        q = quotes.get(norm_hk(sym), {})
        last = q.get("last")
        if last is None:
            print(f"{sym:<8}{'':<9} {'':<3} {'':>4} {'無報價'}")
            continue
        shares = pos["shares"]
        cost = pos["cost_usd"]
        price, src = us_live_price(sym, q, usd_hkd)
        value = shares * price
        cost_total = shares * cost
        pnl = value - cost_total
        pct = pnl_pct(cost_total, value)
        # 今日盈虧：現價 − 昨收（美股含盤後，因 us_live_price 回傳盤後價）
        prev = q.get("previous_close")
        try:
            day = (price - float(prev)) * shares if prev not in (None, "") else None
        except (ValueError, TypeError):
            day = None
        us_total_cost += cost_total
        us_total_value += value
        if day is not None:
            us_total_day += day
        name = sym_name(sym)
        day_s = f"${day:>+11,.2f}" if day is not None else f"{'N/A':>12}"
        print(f"{sym:<8}{name:<9} {'美':<3} {shares:>4} ${cost:>8.2f} ${price:>8.2f} {src:<10}${value:>10,.2f} ${pnl:>+11,.2f} {day_s} {pct:>+6.2f}%")

    if us_total_cost:
        us_pnl = us_total_value - us_total_cost
        print("-" * 99)
        print(f"{'美股合計':<8}{'':<9} {'':<3} {'':>4} {'':>9} {'':>9} {'':<10}${us_total_value:>10,.2f} ${us_pnl:>+11,.2f} ${us_total_day:>+11,.2f} {pnl_pct(us_total_cost, us_total_value):>+6.2f}%")
        print(f"  ≈ HK${us_total_value * usd_hkd:,.0f} (@ {usd_hkd:.2f})；今日盈虧 ≈ HK${us_total_day * usd_hkd:,.0f}")

    # ── 美股 24h 參考價細節（主表現價來源 + Cboe bid/ask；盤前/盤後=CNBC，休市=Cboe） ──
    print()
    print("🌙 美股 24h 參考價細節（主表現價來源；Cboe 延時 ~15min）")
    print("-" * 70)
    for sym in US_POSITIONS:
        q = quotes.get(norm_hk(sym), {})
        price, src = us_live_price(sym, q, usd_hkd)
        cboe = fetch_cboe(sym)
        name = sym_name(sym)
        if cboe:
            line = (f"  {sym:<6} {name:<8} 主表 ${price:>8,.2f}[{src}]"
                    f"  Cboe ${cboe['price']:>8,.2f} [bid/ask {cboe['bid']}/{cboe['ask']}] {cboe['ts']} ET")
        else:
            line = f"  {sym:<6} {name:<8} 主表 ${price:>8,.2f}[{src}]  Cboe 無數據"
        print(line)
    print("  （盤前/盤後用 CNBC 即時價；美股休市時用 Cboe 24h 夜間參考價，非成交價）")

    print()

    # ── 港股 ──
    print("━" * 75)
    print("🇭🇰 港股持倉（今日盈虧日界：UTC+8 04:00；港股昨收為本地收盤）")
    note = section_note(quotes, HK_POSITIONS, "HK")
    if note:
        print(note)
    print("━" * 75)
    print(f"{'代碼':<10} {'名稱':<12} {'市':<3} {'股數':>5} {'成本':>10} {'現價':>10} {'市值':>12} {'持倉盈虧':>12} {'今日盈虧':>12} {'%':>7}")
    print("-" * 88)

    hk_total_cost = 0.0
    hk_total_value = 0.0
    hk_total_day = 0.0
    for sym, pos in HK_POSITIONS.items():
        q = quotes.get(norm_hk(sym), {})
        last = q.get("last")
        if last is None:
            print(f"{sym:<10} {'':<12} {'':<3} {'':>5} {'無報價'}")
            continue
        shares = pos["shares"]
        cost = pos["cost_hkd"]
        value = shares * last
        cost_total = shares * cost
        pnl = value - cost_total
        pct = pnl_pct(cost_total, value)
        prev = q.get("previous_close")
        try:
            day = (last - float(prev)) * shares if prev not in (None, "") else None
        except (ValueError, TypeError):
            day = None
        hk_total_cost += cost_total
        hk_total_value += value
        if day is not None:
            hk_total_day += day
        name = sym_name(sym)
        day_s = f"HK${day:>+10,.0f}" if day is not None else f"{'N/A':>12}"
        print(f"{sym:<10} {name:<12} {'港':<3} {shares:>5} HK${cost:>8.2f} HK${last:>8.2f} HK${value:>10,.0f} HK${pnl:>+10,.0f} {day_s} {pct:>+6.2f}%")

    if hk_total_cost:
        hk_pnl = hk_total_value - hk_total_cost
        print("-" * 88)
        print(f"{'港股合計':<10} {'':<12} {'':<3} {'':>5} {'':>10} {'':>10} HK${hk_total_value:>10,.0f} HK${hk_pnl:>+10,.0f} HK${hk_total_day:>+10,.0f} {pnl_pct(hk_total_cost, hk_total_value):>+6.2f}%")

    print()

    # ── A 股 ──
    print("━" * 75)
    print("🇨🇳 A 股持倉（今日盈虧日界：UTC+8 04:00；A 股昨收為本地收盤）")
    note = section_note(quotes, CN_POSITIONS, "CN")
    if note:
        print(note)
    print("━" * 75)
    print(f"{'代碼':<10} {'名稱':<12} {'市':<3} {'股數':>5} {'成本':>9} {'現價':>9} {'市值':>11} {'持倉盈虧':>11} {'今日盈虧':>11} {'%':>7}")
    print("-" * 88)

    cn_total_cost = 0.0
    cn_total_value = 0.0
    cn_total_day = 0.0
    for sym, pos in CN_POSITIONS.items():
        q = quotes.get(norm_hk(sym), {})
        last = q.get("last")
        if last is None:
            print(f"{sym:<10} {'':<12} {'':<3} {'':>5} {'無報價'}")
            continue
        shares = pos["shares"]
        cost = pos["cost_cny"]
        value = shares * last
        cost_total = shares * cost
        pnl = value - cost_total
        pct = pnl_pct(cost_total, value)
        prev = q.get("previous_close")
        try:
            day = (last - float(prev)) * shares if prev not in (None, "") else None
        except (ValueError, TypeError):
            day = None
        cn_total_cost += cost_total
        cn_total_value += value
        if day is not None:
            cn_total_day += day
        name = sym_name(sym)
        day_s = f"¥{day:>+10,.0f}" if day is not None else f"{'N/A':>11}"
        print(f"{sym:<10} {name:<12} {'A':<3} {shares:>5} ¥{cost:>8.3f} ¥{last:>8.3f} ¥{value:>10,.0f} ¥{pnl:>+10,.0f} {day_s} {pct:>+6.2f}%")

    if cn_total_cost:
        cn_pnl = cn_total_value - cn_total_cost
        print("-" * 88)
        print(f"{'A股合計':<10} {'':<12} {'':<3} {'':>5} {'':>9} {'':>9} ¥{cn_total_value:>10,.0f} ¥{cn_pnl:>+10,.0f} ¥{cn_total_day:>+10,.0f} {pnl_pct(cn_total_cost, cn_total_value):>+6.2f}%")

    print()
    # ── 組合總覽 (HKD 約當) ──
    us_hkd = us_total_value * usd_hkd
    cn_hkd = cn_total_value * cny_hkd  # CNY→HKD
    grand = us_hkd + hk_total_value + cn_hkd + CASH_HKD

    us_cost_hkd = us_total_cost * usd_hkd
    cn_cost_hkd = cn_total_cost * cny_hkd
    grand_cost = us_cost_hkd + hk_total_cost + cn_cost_hkd + CASH_HKD
    grand_pnl = grand - grand_cost

    print("━" * 62)
    print("🏦 組合總覽 (HKD 約當) ｜ 今日盈虧日界 UTC+8 04:00")
    print("━" * 62)
    print(f"  美股:    HK${us_hkd:>12,.0f}   （今日 HK${us_total_day * usd_hkd:>+11,.0f}）")
    print(f"  港股:    HK${hk_total_value:>12,.0f}   （今日 HK${hk_total_day:>+11,.0f}）")
    print(f"  A 股:    HK${cn_hkd:>12,.0f}   （今日 HK${cn_total_day * cny_hkd:>+11,.0f}）")
    print(f"  現金:    HK${CASH_HKD:>12,.2f}")
    print("  ───────────────────────────")
    print(f"  總計:    HK${grand:>12,.0f}")
    if grand_cost:
        print(f"  總成本:  HK${grand_cost:>12,.0f}（匯率：USD/HKD {usd_hkd:.2f}、HKD/CNY {hkd_cny:.4f}）")
        print(f"  未實現盈虧:  HK${grand_pnl:>+12,.0f}（{pnl_pct(grand_cost, grand):+.2f}%，不含已實現）")
        grand_day = us_total_day * usd_hkd + hk_total_day + cn_total_day * cny_hkd
        print(f"  今日盈虧:  HK${grand_day:>+12,.0f}（日界 UTC+8 04:00，美股含盤後）")

    # ── 已實現獲利（已平倉；與 positions.md 同步） ──
    print()
    print("━" * 62)
    print("💰 已實現獲利 (Realized Gains)")
    print("━" * 62)
    realized_total = 0.0
    for g in REALIZED_GAINS:
        amt = g["amount_hkd"]
        if amt is None:
            print(f"  {g['desc']:<24} 待補   （{g['detail']}）")
            continue
        realized_total += amt
        print(f"  {g['desc']:<24} HK${amt:>+10,.0f}   （{g['detail']}）")
    print("-" * 62)
    if CALL_PREMIUM_HKD is None:
        print(f"  已實現小計（未含 Call 權利金）: HK${realized_total:>+10,.0f}")
        print("  ⚠️ 備兌 Call 權利金金額待用戶提供，填妥 scripts/quotes.py 的")
        print("     CALL_PREMIUM_HKD 後自動併入。")
    else:
        print(f"  已實現小計: HK${realized_total:>+10,.0f}")

    # ── 投資收益合計（未實現 + 已實現）＝ 缺口回補基準（deficits.md） ──
    invest_total = grand_pnl + realized_total
    print()
    print("━" * 62)
    print("📈 投資收益合計（未實現 + 已實現）— 缺口回補基準")
    print("━" * 62)
    print(f"  未實現盈利:  HK${grand_pnl:>+12,.0f}")
    print(f"  已實現盈利:  HK${realized_total:>+12,.0f}")
    print(f"  ───────────────────────────")
    print(f"  收益合計:    HK${invest_total:>+12,.0f}")

    # ── 回補進度：由 BASELINE_DATE 基準線 0 起計 ──
    net = net_recovery(invest_total)
    print()
    print(f"  基準線({BASELINE_DATE}):  HK${BASELINE_INCOME:>+12,.0f}"
          f"  ← 已計入 2026 缺口，進度 0")
    print(f"  淨回補額:    HK${net:>+12,.0f}")
    print(f"  年終目標:    {FLOOR_TARGET:,.0f}（硬下限）/ {HALF_TARGET:,.0f}"
          f"（缺口一半；總缺口 {TOTAL_DEFICIT:,.0f}）")
    print(f"  回補進度:    {net / FLOOR_TARGET * 100:.1f}% of {FLOOR_TARGET:,.0f}"
          f" ｜ {net / HALF_TARGET * 100:.1f}% of {HALF_TARGET:,.0f}")
    print(f"  仲差:        HK${max(FLOOR_TARGET - net, 0):,.0f}（距硬下限）"
          f" / HK${max(HALF_TARGET - net, 0):,.0f}（距一半）")
    if MONTHS_LEFT > 0:
        print(f"  月均需賺:    HK${max(FLOOR_TARGET - net, 0) / MONTHS_LEFT:,.0f}（距硬下限）"
              f" / HK${max(HALF_TARGET - net, 0) / MONTHS_LEFT:,.0f}（距一半）")


if __name__ == "__main__":
    main()
