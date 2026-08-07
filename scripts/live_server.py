#!/usr/bin/env python3
"""
即時組合報價儀表板
用法: python3 scripts/live_server.py [--port PORT]
然後瀏覽器打開 http://localhost:PORT

後端：CNBC 即時報價 API（免登入）+ open.er-api.com 匯率
前端：每 30 秒自動刷新，無需手動 reload
"""

import http.server
import json
import urllib.request
import urllib.parse
import ssl
import time
import sys
import threading
from datetime import datetime, timezone, timedelta

# ── Config ──
PORT = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == '--port' else 8999
REFRESH_SECONDS = 30
HKT = timezone(timedelta(hours=8))

# ── 持倉數據（與 positions.md / scripts/quotes.py 同步） ──
# ⚠️ 模板預設值（空白）— 請填入你自己的資料，或參考 scripts/quotes.py 的持倉字典：
POSITIONS = [
    # {"sym": "AAPL",     "name": "蘋果",        "mkt": "US", "shares": 10,  "cost": 180.00, "ccy": "USD"},
    # {"sym": "0700.HK",  "name": "騰訊控股",    "mkt": "HK", "shares": 100, "cost": 380.00, "ccy": "HKD"},
    # {"sym": "159781.SZ","name": "科創創業50ETF", "mkt": "CN", "shares": 5000, "cost": 1.05, "ccy": "CNY"},
]

CASH_HKD = 0.0  # 模板預設值 — 請填你的現金餘額（HKD）

# CNBC 狀態碼正規化（前端 CSS class 用簡寫）
_STATUS_MAP = {
    "REG_MKT": "REG", "PRE_MKT": "PRE", "POST_MKT": "POST",
    "CLOSED": "CLOSED", "POST_MKT_PREV": "CLOSED",
}
REALIZED_HKD = 0.0  # 模板預設值 — 已實現獲利（已平倉收益，HKD）

# ── FX 快取（每 10 分鐘更新一次） ──
_fx_cache = {"data": None, "ts": 0}

def _cnbc_sym(sym: str) -> str:
    """內部代碼轉 CNBC 格式（港股去前導零）。"""
    if sym.endswith(".HK"):
        num = sym.split(".")[0].lstrip("0")
        return f"{num}.HK"
    return sym

def _fetch_json(url: str, insecure: bool = False) -> dict:
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return json.loads(resp.read().decode())

# ── CNBC 即時報價（批次一次拉完） ──
def fetch_cnbc(symbols: list) -> dict[str, dict]:
    sym_str = "|".join(_cnbc_sym(s) for s in symbols)
    url = (
        "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
        f"?symbols={urllib.parse.quote(sym_str, safe='|')}"
        "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"
        f"&_={int(time.time() * 1000)}"
    )
    data = _fetch_json(url)
    result = {}
    for q in data.get("FormattedQuoteResult", {}).get("FormattedQuote", []):
        s = q["symbol"].upper()
        result[s] = {
            "last": q.get("last"),
            "change": q.get("change"),
            "change_pct": q.get("change_pct"),
            "prev_close": q.get("previous_day_closing"),
            "ccy": q.get("currencyCode", "USD"),
            "status": q.get("curmktstatus", "CLOSED"),
            "time": q.get("last_timedate", ""),
        }
    return result

# ── 即時匯率（er-api.com，免 key，每 10 分鐘快取） ──
def fetch_fx() -> dict:
    global _fx_cache
    now = time.time()
    if _fx_cache["data"] and now - _fx_cache["ts"] < 600:
        return _fx_cache["data"]
    try:
        data = _fetch_json("https://open.er-api.com/v6/latest/USD", insecure=True)
        rates = data.get("rates", {})
        usd_hkd = rates.get("HKD", 7.84)
        usd_cny = rates.get("CNY", 7.25)
        hkd_cny = usd_cny / usd_hkd if usd_hkd else 0.92
        fx = {
            "usd_hkd": round(usd_hkd, 4),
            "hkd_cny": round(hkd_cny, 4),
            "cny_hkd": round(1 / hkd_cny, 4) if hkd_cny else 1.16,
        }
        _fx_cache = {"data": fx, "ts": now}
        return fx
    except Exception:
        # 降級使用上次快取或預設值
        if _fx_cache["data"]:
            return _fx_cache["data"]
        return {"usd_hkd": 7.8447, "hkd_cny": 0.8622, "cny_hkd": 1.1599}

# ── HKD 換算 ──
def _to_hkd(amount: float, ccy: str, fx: dict) -> float:
    if ccy == "HKD":
        return amount
    if ccy == "USD":
        return amount * fx["usd_hkd"]
    if ccy == "CNY":
        return amount * fx["cny_hkd"]
    return amount

# ── 建構組合數據 ──
def build_portfolio() -> dict:
    symbols = [p["sym"] for p in POSITIONS]
    quotes = fetch_cnbc(symbols)
    fx = fetch_fx()
    t = datetime.now(HKT)

    rows = []
    total_value = 0.0
    total_cost = 0.0
    total_day = 0.0
    total_pnl = 0.0

    for p in POSITIONS:
        cnbc_s = _cnbc_sym(p["sym"])
        q = quotes.get(cnbc_s, {})
        last = q.get("last")
        prev = q.get("prev_close")

        if last is None:
            rows.append({**p, "price": None, "prev": None, "error": "無報價"})
            continue

        price = float(last)
        prev_close = float(prev) if prev else 0.0
        shares = p["shares"]
        cost = p["cost"]
        ccy = p["ccy"]

        val_local = shares * price
        cost_local = shares * cost
        pnl_local = val_local - cost_local
        day_local = (price - prev_close) * shares if prev_close else 0.0

        val_hkd = _to_hkd(val_local, ccy, fx)
        cost_hkd = _to_hkd(cost_local, ccy, fx)
        pnl_hkd = _to_hkd(pnl_local, ccy, fx)
        day_hkd = _to_hkd(day_local, ccy, fx)

        total_value += val_hkd
        total_cost += cost_hkd
        total_day += day_hkd
        total_pnl += pnl_hkd

        rows.append({
            **p,
            "price": price,
            "prev": prev_close,
            "change_pct": q.get("change_pct"),
            "status": _STATUS_MAP.get(q.get("status", ""), "CLOSED"),
            "val_local": val_local,
            "val_hkd": round(val_hkd, 0),
            "cost_hkd": round(cost_hkd, 0),
            "pnl_hkd": round(pnl_hkd, 0),
            "pnl_pct": (pnl_local / cost_local * 100) if cost_local else 0,
            "day_hkd": round(day_hkd, 0),
        })

    rows.sort(key=lambda r: r.get("val_hkd", 0), reverse=True)

    total_value += CASH_HKD
    pct = (total_pnl / total_cost * 100) if total_cost else 0

    return {
        "timestamp": t.strftime("%Y-%m-%d %H:%M:%S HKT"),
        "ts_unix": t.timestamp(),
        "fx": fx,
        "rows": rows,
        "summary": {
            "total_value": round(total_value, 0),
            "total_cost": round(total_cost, 0),
            "total_pnl": round(total_pnl, 0),
            "total_pnl_pct": round(pct, 2),
            "total_day": round(total_day, 0),
            "cash": CASH_HKD,
            "realized": REALIZED_HKD,
            "total_gains": round(total_pnl + REALIZED_HKD, 0),
        },
    }

# ── HTML 儀表板（內嵌） ──
HTML = rf"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>持倉即時報價</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,"Microsoft JhengHei","PingFang HK",sans-serif;background:#f2f3f7;color:#1e1e1e;padding:24px}}
  .wrap{{max-width:1024px;margin:0 auto}}
  header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px}}
  h1{{font-size:22px;font-weight:800;letter-spacing:-0.3px}}
  .live{{font-size:13px;color:#888;display:flex;align-items:center;gap:6px}}
  .live .dot{{width:8px;height:8px;border-radius:50%;background:#22c55e;animation:pulse 1.5s infinite;display:inline-block}}
  .live .dot.err{{background:#ef4444;animation:none}}
  @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}

  .bar{{height:3px;background:#e0e0e0;border-radius:2px;margin-bottom:20px;overflow:hidden}}
  .bar-fill{{height:100%;background:#22c55e;border-radius:2px;transition:width .15s linear}}

  .cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px}}
  .card{{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.04);display:flex;flex-direction:column;gap:2px}}
  .card .lbl{{font-size:11px;color:#999;text-transform:uppercase;letter-spacing:.3px}}
  .card .val{{font-size:22px;font-weight:800}}
  .card .sub{{font-size:12px;color:#888}}
  .up{{color:#22c55e}}.down{{color:#ef4444}}

  table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
  th{{background:#f7f8fa;font-size:12px;font-weight:600;color:#777;padding:10px 8px;text-align:right;border-bottom:1px solid #eee}}
  th:nth-child(1),th:nth-child(2){{text-align:left}}
  td{{padding:10px 8px;font-size:14px;text-align:right;border-bottom:1px solid #f2f2f2;font-variant-numeric:tabular-nums}}
  td:nth-child(1),td:nth-child(2){{text-align:left}}
  td.code{{font-weight:700;font-size:13px}}
  td.name{{font-size:12px;color:#777}}
  tr:hover{{background:#fafcff}}
  tr.tot{{font-weight:800;background:#f7f8fa}}
  tr.tot td{{border-top:2px solid #ddd}}
  .st{{font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}}
  .st-REG{{background:#22c55e18;color:#15803d}}.st-PRE{{background:#f59e0b18;color:#b45309}}
  .st-POST{{background:#3b82f618;color:#1d4ed8}}.st-CLOSED{{background:#9ca3af18;color:#6b7280}}
  .note{{font-size:11px;color:#aaa;margin-top:12px;text-align:center}}

  @media(max-width:780px){{
    body{{padding:12px}}
    .cards{{grid-template-columns:repeat(2,1fr)}}
    td,th{{font-size:12px;padding:8px 4px}}
  }}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>📊 持倉即時報價</h1>
  <div class="live"><span class="dot" id="dot"></span><span id="age">更新中…</span></div>
</header>
<div class="bar"><div class="bar-fill" id="bar" style="width:0"></div></div>
<div class="cards" id="cards"></div>
<table><thead>
<tr><th>代碼</th><th>名稱</th><th>股數</th><th>成本</th><th>現價</th><th>狀態</th><th>市值(HKD)</th><th>盈虧</th><th>%</th><th>今日</th></tr>
</thead><tbody id="body"></tbody></table>
<div class="note">⚠️ 美股：盤前(PRE)／盤後(POST)即時價、常規(REG)成交價。日界 UTC+8 04:00。綠漲紅跌。</div>
</div>
<script>
const R={{REFRESH_SECONDS}};
var fail=0, barTimer=null;

function F(n,d){{return n==null?'—':Number(n).toLocaleString('zh-HK',{{minimumFractionDigits:d||0,maximumFractionDigits:d||0}})}}
function P(n){{return n==null?'—':(n>=0?'+':'')+n.toFixed(2)+'%'}}
function C(n){{return n==null?'':(n>=0?'up':'down')}}
function HK(n){{return n==null?'—':'HK$'+Math.round(n).toLocaleString('zh-HK')}}
function CY(n,c){{if(n==null)return'—';if(c=='USD')return'$'+n.toFixed(2);if(c=='HKD')return'HK$'+n.toFixed(2);if(c=='CNY')return'¥'+n.toFixed(3);return String(n)}}

function render(d){{
  var s=d.summary;
  var cs=[["總組合值",HK(s.total_value),'成本 '+HK(s.total_cost),''],
          ["未實現盈虧",HK(s.total_pnl),P(s.total_pnl_pct),C(s.total_pnl)],
          ["今日盈虧",HK(s.total_day),'日界 UTC+8 04:00',C(s.total_day)],
          ["已實現",HK(s.realized),'已平倉收益',C(s.realized)],
          ["現金",HK(s.cash),'收益合計 '+HK(s.total_gains),'']];
  document.getElementById('cards').innerHTML=cs.map(function(c){{return'<div class="card"><div class="lbl">'+c[0]+'</div><div class="val '+c[3]+'">'+c[1]+'</div><div class="sub">'+c[2]+'</div></div>'}}).join('');

  var h='';
  for(var i=0;i<d.rows.length;i++){{
    var r=d.rows[i];
    if(r.error){{h+='<tr><td class="code">'+r.sym+'</td><td class="name">'+r.name+'</td><td>'+r.shares+'</td><td colspan="7">'+r.error+'</td></tr>';continue}}
    var st=r.status||'CLOSED',sm={{REG:'盤中',PRE:'盤前',POST:'盤後',CLOSED:'收市'}};
    h+='<tr><td class="code">'+r.sym+'</td><td class="name">'+r.name+'</td>';
    h+='<td>'+r.shares+'</td><td>'+CY(r.cost,r.ccy)+'</td><td>'+CY(r.price,r.ccy)+'</td>';
    h+='<td><span class="st st-'+st+'">'+(sm[st]||st)+'</span></td>';
    h+='<td>'+HK(r.val_hkd)+'</td><td class="'+C(r.pnl_hkd)+'">'+HK(r.pnl_hkd)+'</td>';
    h+='<td class="'+C(r.pnl_hkd)+'">'+P(r.pnl_pct)+'</td><td class="'+C(r.day_hkd)+'">'+HK(r.day_hkd)+'</td></tr>';
  }}
  h+='<tr class="tot"><td colspan="6">合計（含現金 '+HK(s.cash)+'）</td><td>'+HK(s.total_value)+'</td><td class="'+C(s.total_pnl)+'">'+HK(s.total_pnl)+'</td><td class="'+C(s.total_pnl)+'">'+P(s.total_pnl_pct)+'</td><td class="'+C(s.total_day)+'">'+HK(s.total_day)+'</td></tr>';
  document.getElementById('body').innerHTML=h;
  document.getElementById('age').textContent='即時 ('+d.timestamp.split(' ')[1]+')';
}}

async function tick(){{
  var dot=document.getElementById('dot'),bar=document.getElementById('bar');
  dot.className='dot';
  if(barTimer)clearInterval(barTimer);
  var w=0;bar.style.width='0';bar.style.background='#22c55e';
  barTimer=setInterval(function(){{w+=1;bar.style.width=w+'%';if(w>=99)clearInterval(barTimer)}},R*10);

  try{{
    var resp=await fetch('/api/quotes');
    if(!resp.ok)throw new Error(resp.status);
    render(await resp.json());
    fail=0;dot.className='dot';bar.style.width='100%';
    setTimeout(function(){{bar.style.width='0'}},200);
  }}catch(e){{
    fail++;dot.className='dot err';
    document.getElementById('age').textContent=fail>2?'連線異常':'重試中 ×'+fail;
    bar.style.width='100%';bar.style.background='#ef4444';
    setTimeout(function(){{bar.style.background='#e0e0e0'}},600);
  }}
}}

tick();
setInterval(tick,R*1000);
</script>
</body>
</html>"""

# ── HTTP Handler ──
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/quotes":
            try:
                data = build_portfolio()
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # 靜音，不印 log

# ── 啟動 ──
def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"🚀  組合即時報價儀表板")
    print(f"    位址 → http://localhost:{PORT}")
    print(f"    刷新 → 每 {REFRESH_SECONDS} 秒")
    print(f"    停止 → Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 已停止")

if __name__ == "__main__":
    main()
