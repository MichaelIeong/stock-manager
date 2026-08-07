#!/usr/bin/env python3
"""組合預期年化報酬模型（自下而上，逐檔估值）。

⚠️ 方法論：
    不用「感覺」或者「歷史平均」估算出來。每檔股用可驗證的估值恆等式：

        1 年總報酬 ≈ (前瞻EPS × 目標PE) / 現價 − 1 + 股息率
                    └─ 盈利增長 ─┘   └ 估值變動 ┘

    虧損股（如虧損的成長股）改用 P/S 錨定：
        1 年總報酬 ≈ (每股營收 × (1+營收增長) × 目標P/S) / 現價 − 1

    ETF 沒有個股基本面，用指數層面假設（價格報酬 + 股息率）。

📊 硬數據來源：CNBC restQuote（price / eps / feps / pe / fpe / psales /
    revenuettm / sharesout / dividendyield），逐日存檔於 DATA/。
🧠 假設部分：目標 PE／增長率／目標 P/S 為**判斷值**，全部集中在 ASSUMPTIONS，
    可逐項覆核與修改。每項都寫下理據，不准無根據憑空猜測。

用法：
    python3 scripts/expected_return.py
    python3 scripts/expected_return.py --scenario bull      # 只看單一情境
    python3 scripts/expected_return.py --deploy-cash        # 假設現金全數入市
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quotes import (  # noqa: E402
    US_POSITIONS, HK_POSITIONS, CN_POSITIONS, CASH_HKD,
    norm_hk, fetch_fx, find_latest_quotes, sym_name, us_live_price,
)

SCENARIOS = ["bear", "base", "bull"]
SC_LABEL = {"bear": "熊市", "base": "基準", "bull": "牛市"}

# ══════════════════════════════════════════════════════════════════
# 假設表 — 每項都要有理據，改動請一併更新 note
# ══════════════════════════════════════════════════════════════════
#   method:  "pe"  → 用 前瞻EPS × 目標PE
#            "ps"  → 用 每股營收 × (1+增長) × 目標P/S   （虧損股）
#            "tp"  → 直接用目標價（錨定券商一致預期，虧損股適用）
#            "idx" → 直接用指數價格報酬假設            （ETF）
#   eps_growth:   若 CNBC 有 feps 就不必填（自動用 feps）；沒有先用這個覆蓋 TTM EPS
#   eps_override: CNBC 數據過時／口徑不符時，用外部來源覆蓋 EPS 基數（須在 note 交代出處）
ASSUMPTIONS = {}  # 模板預設值（空白）— 請填入你自己的資料

CASH_RETURN = 0.0  # 現金閒置，假設零報酬（保守）


def parse_pct(v):
    if not v or v in ("—", "N/A"):
        return None
    try:
        return float(str(v).replace("%", "").replace(",", "")) / 100
    except ValueError:
        return None


def parse_num(v):
    if v in (None, "", "—", "N/A"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def parse_big(v):
    """'429.03B' / '3.62T' → float"""
    if not v or v in ("—", "N/A"):
        return None
    s = str(v).replace(",", "").strip()
    mult = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
    if s and s[-1].upper() in mult:
        try:
            return float(s[:-1]) * mult[s[-1].upper()]
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def load_fundamentals(path: str, usd_hkd: float = 7.844) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for q in data.get("FormattedQuoteResult", {}).get("FormattedQuote", []):
        sym = norm_hk(q.get("symbol", ""))
        raw_last = parse_num(q.get("last"))
        price = raw_last
        # 美股未開盤：主表現價改用盤前/盤後 CNBC 即時價或 Cboe 24h 夜間參考價
        if sym in US_POSITIONS:
            ext = (q.get("ExtendedMktQuote") or {})
            q_compat = {
                "last": raw_last,
                "status": q.get("curmktstatus", ""),
                "ext_type": ext.get("type", ""),
                "ext_last": ext.get("last"),
            }
            price, _ = us_live_price(sym, q_compat, usd_hkd)
        out[sym] = {
            "name": q.get("name"),
            "price": price,
            "eps": parse_num(q.get("eps")),
            "feps": parse_num(q.get("feps")),
            "pe": parse_num(q.get("pe")),
            "fpe": parse_num(q.get("fpe")),
            "psales": parse_num(q.get("psales")),
            "revenue": parse_big(q.get("revenuettm")),
            "shares": parse_big(q.get("sharesout")),
            "div": parse_pct(q.get("dividendyield")) or 0.0,
            "ccy": q.get("currencyCode"),
        }
    return out


def expected_return(sym: str, f: dict, sc: str):
    """回傳 (總報酬率, 說明字串)。"""
    a = ASSUMPTIONS.get(sym)
    if not a or not f.get("price"):
        return None, "無假設/無報價"
    price, div = f["price"], f["div"]

    if a["method"] == "idx":
        return a["price_return"][sc] + div, f"指數 {a['price_return'][sc]:+.0%} + 息 {div:.2%}"

    if a["method"] == "tp":
        tp = a["target_price"][sc]
        return tp / price - 1 + div, f"目標價 {tp:.2f}（券商錨定）"

    if a["method"] == "ps":
        if not (f["revenue"] and f["shares"]):
            return None, "缺營收/股數"
        rps = f["revenue"] / f["shares"]
        fwd_rps = rps * (1 + a["rev_growth"][sc])
        target = fwd_rps * a["target_ps"][sc]
        return target / price - 1 + div, \
            f"每股營收 {rps:.2f}→{fwd_rps:.2f} × P/S {a['target_ps'][sc]:.2f} = {target:.2f}"

    # method == "pe"
    if "eps_growth" in a:
        base_eps = a.get("eps_override", f["eps"])
        if base_eps is None:
            return None, "缺 EPS"
        tag = "外部EPS" if "eps_override" in a else "TTM EPS"
        fwd_eps = base_eps * (1 + a["eps_growth"][sc])
        src = f"{tag} {base_eps:.2f}×(1{a['eps_growth'][sc]:+.0%})"
    else:
        fwd_eps = f["feps"]
        if fwd_eps is None:
            return None, "缺前瞻 EPS"
        src = f"feps {fwd_eps:.2f}"
    target = fwd_eps * a["target_pe"][sc]
    return target / price - 1 + div, \
        f"{src} × PE {a['target_pe'][sc]:.0f} = {target:.2f}"


def main():
    ap = argparse.ArgumentParser(description="組合預期年化報酬模型")
    ap.add_argument("quotes_path", nargs="?", default=None)
    ap.add_argument("--scenario", choices=SCENARIOS, default=None)
    ap.add_argument("--deploy-cash", action="store_true",
                    help="假設現金全數投入市場（按現持倉比例攤分）")
    args = ap.parse_args()

    usd_hkd, hkd_cny = fetch_fx()
    path = args.quotes_path or find_latest_quotes()
    fund = load_fundamentals(path, usd_hkd)

    # ── 建立持倉市值（HKD） ──
    holdings = []
    for sym, p in US_POSITIONS.items():
        f = fund.get(sym, {})
        if f.get("price"):
            holdings.append((sym, f, p["shares"] * f["price"] * usd_hkd))
    for sym, p in HK_POSITIONS.items():
        f = fund.get(norm_hk(sym), {})
        if f.get("price"):
            holdings.append((norm_hk(sym), f, p["shares"] * f["price"]))
    for sym, p in CN_POSITIONS.items():
        f = fund.get(sym, {})
        if f.get("price"):
            holdings.append((sym, f, p["shares"] * f["price"] / hkd_cny))

    equity_value = sum(v for _, _, v in holdings)
    cash = 0.0 if args.deploy_cash else CASH_HKD
    total = equity_value + cash

    print("━" * 86)
    print(f"📊 組合預期年化報酬模型　｜　報價檔：{Path(path).name}"
          f"　｜　USD/HKD {usd_hkd:.4f}")
    print("━" * 86)
    if args.deploy_cash:
        print(f"  ⚙️  假設現金 HK${CASH_HKD:,.0f} 已全數入市（按現持倉比例攤分）")
    print(f"  股票市值 HK${equity_value:,.0f}　+　現金 HK${cash:,.0f}"
          f"　=　總值 HK${total:,.0f}")
    print()

    scens = [args.scenario] if args.scenario else SCENARIOS

    # ── 逐檔明細 ──
    hdr = f"  {'標的':<11}{'名稱':<12}{'市值(HK$)':>12}{'權重':>8}"
    for sc in scens:
        hdr += f"{SC_LABEL[sc]:>10}"
    print(hdr)
    print("-" * 98)

    weighted = {sc: 0.0 for sc in scens}
    rows = []
    for sym, f, val in sorted(holdings, key=lambda x: -x[2]):
        w = val / total
        name = sym_name(sym)
        line = f"  {sym:<11}{name:<12}{val:>12,.0f}{w:>7.1%} "
        detail = {}
        for sc in scens:
            r, why = expected_return(sym, f, sc)
            detail[sc] = (r, why)
            if r is None:
                line += f"{'—':>10}"
            else:
                line += f"{r:>+9.1%} "
                weighted[sc] += w * r
        print(line)
        rows.append((sym, f, detail))

    if cash > 0:
        line = f"  {'現金':<11}{'':<12}{cash:>12,.0f}{cash/total:>7.1%} "
        for sc in scens:
            line += f"{CASH_RETURN:>+9.1%} "
            weighted[sc] += (cash / total) * CASH_RETURN
        print(line)

    print("-" * 98)
    line = f"  {'組合合計':<11}{'':<12}{total:>12,.0f}{1.0:>7.1%} "
    for sc in scens:
        line += f"{weighted[sc]:>+9.1%} "
    print(line)
    print()

    # ── 換算成金額 ──
    print("── 預期 1 年收益金額（以現有本金 HK$%s 計，未加月供） ──" % f"{total:,.0f}")
    for sc in scens:
        print(f"  {SC_LABEL[sc]:<6} 年化 {weighted[sc]:>+7.1%}"
              f"　→　HK${weighted[sc]*total:>+11,.0f}")
    print()

    # ── 貢獻度：哪隻真正推動組合 ──
    if len(scens) == len(SCENARIOS):
        print("── 貢獻度分析（權重 × 報酬 = 對組合實際貢獻 HK$） ──")
        print(f"  {'標的':<11}{'名稱':<12}{'權重':>7}{'熊市':>11}{'基準':>11}{'牛市':>11}"
              f"{'牛熊擺幅':>11}")
        print("-" * 98)
        contrib = []
        for sym, f, detail in rows:
            w = next(v for s, _, v in holdings if s == sym) / total
            c = {sc: (detail[sc][0] or 0) * w * total for sc in SCENARIOS}
            contrib.append((sym, w, c, c["bull"] - c["bear"]))
        for sym, w, c, swing in sorted(contrib, key=lambda x: -x[3]):
            name = sym_name(sym)
            print(f"  {sym:<11}{name:<12}{w:>6.1%}{c['bear']:>+11,.0f}{c['base']:>+11,.0f}"
                  f"{c['bull']:>+11,.0f}{swing:>11,.0f}")
        print("-" * 86)
        if cash > 0:
            print(f"  現金 HK${cash:,.0f}（{cash/total:.1%}）三個情境都貢獻 0 —— "
                  f"純拖累組合報酬 {weighted['base']*cash/total/max(weighted['base'],1e-9):.0%}")

        # ── 機率加權期望值 ──
        prob = {"bear": 0.25, "base": 0.50, "bull": 0.25}
        ev = sum(prob[sc] * weighted[sc] for sc in SCENARIOS)
        sd = sum(prob[sc] * (weighted[sc] - ev) ** 2 for sc in SCENARIOS) ** 0.5
        print()
        print(f"── 機率加權期望值（熊 25% / 基準 50% / 牛 25%） ──")
        print(f"  期望年化 {ev:+.1%}　→　HK${ev*total:+,.0f}／年"
              f"　｜　情境標準差 {sd:.1%}")

        # ── 映射到缺口目標 ──
        try:
            from recovery import gain, months_to_target
            from deficit import FLOOR_TARGET, HALF_TARGET, TOTAL_DEFICIT
            monthly = 20000.0  # 模板預設值（每月加倉金額，請依你的計劃調整）
            months_left = 5  # 模板預設值（剩餘月數，請依你的計劃調整）
            print()
            print(f"── 映射到缺口回補目標（月供 {monthly:,.0f}，年底剩 {months_left} 個月） ──")
            print(f"  {'情境':<8}{'年化':>9}{'{months_left}個月收益':>13}{'達硬下限':>10}"
                  f"{'達一半':>10}{'達全額':>10}")
            print("-" * 86)
            for sc, label in [("bear", "熊市"), ("base", "基準"),
                              ("bull", "牛市"), ("ev", "期望值")]:
                ann = ev if sc == "ev" else weighted[sc]
                r = (1 + ann) ** (1 / 12) - 1 if ann > -1 else -0.99
                g5 = gain(total, monthly, months_left, r)
                def mt(t):
                    m = (months_to_target(t, total, monthly, ann, cap_months=240)
                         if ann > 0 else None)
                    return f"{m} 個月" if m else "達不到"
                print(f"  {label:<8}{ann:>+8.1%}{g5:>+13,.0f}"
                      f"{mt(FLOOR_TARGET):>10}{mt(HALF_TARGET):>10}"
                      f"{mt(TOTAL_DEFICIT):>10}")
            print("-" * 86)
            print(f"  目標：硬下限 {FLOOR_TARGET:,.0f}｜缺口一半 {HALF_TARGET:,.0f}"
                  f"｜全額 {TOTAL_DEFICIT:,.0f}")
        except ImportError:
            pass
        print()

    # ── 假設理據 ──
    print("── 逐檔理據（🧠=判斷值，📊=CNBC 硬數據） ──")
    for sym, f, detail in rows:
        a = ASSUMPTIONS.get(sym, {})
        name = sym_name(sym)
        pe_txt = f"PE {f['pe']:.1f}" if f.get("pe") else "PE —"
        fpe_txt = f"／fPE {f['fpe']:.1f}" if f.get("fpe") else ""
        print(f"\n  ● {sym} {name}　📊 現價 {f['price']:.2f} {f['ccy']}"
              f"　{pe_txt}{fpe_txt}　息 {f['div']:.2%}")
        print(f"     🧠 {a.get('note','')}")
        for sc in scens:
            r, why = detail[sc]
            if r is not None:
                print(f"        {SC_LABEL[sc]}：{why}　→　{r:+.1%}")
    print("━" * 86)

    return weighted


if __name__ == "__main__":
    main()
