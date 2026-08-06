# stock-manager

AI 輔助的**個人投資組合分析框架**——用來追蹤美股、港股、A 股的持倉盈虧、缺口回補進度與預期報酬。

> ⚠️ 本倉庫**不含任何個人資料**。所有持倉、觀察清單、缺口、計劃都需由你自行填入（見下方「快速上手」）。這是一個「空白模板 + 工具腳本 + AI 提示詞」的框架，clone / fork 之後填你自己的數字即可使用。

---

## 目錄結構

```
stock-manager/
├── AGENTS.md                       # AI 工作區常駐手冊（運作規則、報價來源、檢查清單）
├── README.md                      # 本文件
├── .gitignore
├── scripts/                       # 數學計算腳本（必須用腳本算，禁止手算）
│   ├── cost.py                    # 加倉後加權平均成本
│   ├── quotes.py                  # 全組合 P&L + 美股 24h 參考價（主力）
│   ├── deficit.py                 # 缺口帳本（單一事實來源）
│   ├── recovery.py                # 缺口回補難度模型（帶每月加倉複利）
│   └── expected_return.py         # 自下而上預期年化報酬模型
├── skills/                        # 可直接給 AI 使用的技能
│   ├── stock-analysis/            # 個股 / 加密貨幣分析（8 維評分、組合、熱門掃描、傳聞探測）
│   ├── us-stock-analysis/         # 美股深度分析（基本面 / 技術面 / 估值 / 對比）
│   └── fx-rates/                  # 實時匯率查詢（免 API key）
└── DATA/                          # （你建立）每日即時報價快照存檔，格式 quotes_YYYY-MM-DD.json
```

---

## 環境需求

- **Python 3.10+**（腳本用 `pathlib`、`argparse` 等標準庫，無額外 pip 依賴）
- **curl**（用於拉取 CNBC / Cboe 報價；macOS / Linux 內建）
- **網絡連線**（報價與匯率來自公開免登入 API）
- 可選：**支援 AGENTS.md 的 AI 工具**（WorkBuddy / CodeBuddy 等），用來對話式分析

---

## 快速上手（5 步）

### 1. 填入你的持倉與基本資料

編輯 `scripts/quotes.py`，在檔案頂部的常數填入你的資料：

```python
US_POSITIONS = {
    "MSFT": {"shares": 10, "cost_usd": 420.50},
    "NVDA": {"shares": 5,  "cost_usd": 110.00},
}

HK_POSITIONS = {
    "700.HK":  {"shares": 100, "cost_hkd": 380.00},
    "3690.HK": {"shares": 200, "cost_hkd": 140.00},
}

CN_POSITIONS = {
    "159781.SZ": {"shares": 5000, "cost_cny": 1.05},
}

SYMBOL_NAMES = {            # A 股 / 港股必須有中文名（報表顯示用）
    "700.HK":  "騰訊控股",
    "3690.HK": "美團",
    "159781.SZ": "科創創業50ETF",
}

CASH_HKD = 0.0              # 現金倉（HKD）
```

> 每個市場的成本欄位不同：美股用 `cost_usd`、港股用 `cost_hkd`、A 股用 `cost_cny`。
> 加倉後記得同步更新 `positions` 字典（先用 `cost.py` 算新均價）。

### 2. 拉取即時報價

用 CNBC 開放 API（免登入、免 key）把報價存進 `DATA/`：

```bash
mkdir -p DATA
curl -sS -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=AAPL|MSFT|0700.HK|159781.SZ&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&_=$(date +%s%N)" \
  > "DATA/quotes_$(date +%Y-%m-%d).json"
```

- 多標的：用 `|` 串接，例如 `MSFT|GOOGL|NVDA`。
- 市場代碼：美股直接寫代號；港股加 `.HK`（如 `700.HK`，前導零會自動處理）；A 股加 `.SS` / `.SZ`（如 `159781.SZ`）。
- 結尾 `&_=$(date +%s%N)` 用來**破除 CDN 快取**，每次拉取都要加。
- 拉完建議驗證標的齊全：

```bash
python3 -c "import json; d=json.load(open('DATA/quotes_$(date +%Y-%m-%d).json')); print([q['symbol'] for q in d['FormattedQuoteResult']['FormattedQuote']])"
```

> 美股未開盤時，`quotes.py` 主表「現價」會自動改用盤前／盤後 CNBC 即時價，或 Cboe 24 小時夜間參考價（非昨收），並在「來源」欄標註。

### 3. 計算組合盈虧

```bash
python3 scripts/quotes.py
# 或指定報價檔：
python3 scripts/quotes.py DATA/quotes_2026-08-07.json
```

輸出每檔持倉的現價、成本、市值、盈虧、漲跌%，以及各市場與全組合合計。匯率由 `quotes.py` 自動從 er-api 拉取。

### 4. 缺口帳本與回補進度

如果你有「要賺回來的缺口」（例如過往投機虧損），先在 `scripts/deficit.py` 填：

```python
DEFICITS = [
    {"year": 2026, "amount": 17538.0, "recovered": 0.0, "note": "年初缺口"},
]
FLOOR_TARGET  = 0.0       # 硬下限目標
MONTHS_LEFT   = 5          # 剩餘月份
BASELINE_DATE = "2026-08-06"
BASELINE_INCOME = 0.0      # 基準日當日投資收益（回補進度由 0 起計）
```

```bash
python3 scripts/deficit.py        # 只印帳本與目標
python3 scripts/deficit.py 15415  # 帶入當前投資收益，印回補進度
```

再用 `recovery.py` 算「需要幾多報酬率才能補完」：

```bash
python3 scripts/recovery.py                          # 用預設值
python3 scripts/recovery.py --capital 279872 --monthly 20000 --months 5
python3 scripts/recovery.py --cash 45296             # 現金閒置版（不投入市場）
python3 scripts/recovery.py --start-of-month         # 月供改為月初投入
```

### 5. 預期年化報酬

```bash
python3 scripts/expected_return.py            # 三情境機率加權
python3 scripts/expected_return.py --scenario bull   # 只睇單一情境
python3 scripts/expected_return.py --deploy-cash     # 假設現金全數入市
```

估值假設（目標 PE / 增長率 / 目標 P/S）集中在 `expected_return.py` 的 `ASSUMPTIONS` 字典，可自行逐項覆核修改。

---

## 腳本用法一覽

| 腳本 | 用途 | 用法 |
|---|---|---|
| `cost.py` | 加倉後加權平均成本 | `python3 scripts/cost.py <舊股數> <舊均價> <新股數> <新成交價>` |
| `quotes.py` | 全組合 P&L + 美股 24h 參考價 + 匯率 | `python3 scripts/quotes.py [報價JSON]` |
| `deficit.py` | 缺口帳本 / 回補進度 | `python3 scripts/deficit.py [當前投資收益]` |
| `recovery.py` | 缺口回補難度（帶月供複利） | `python3 scripts/recovery.py [--capital N] [--monthly N] [--months N] [--cash N]` |
| `expected_return.py` | 預期年化報酬模型 | `python3 scripts/expected_return.py [--scenario bear\|base\|bull] [--deploy-cash]` |
| `fx-rates/scripts/fx.py` | 實時匯率（免 key） | `python3 skills/fx-rates/scripts/fx.py [幣種對...\|all]` |

### 成本計算範例

```bash
python3 scripts/cost.py 9 329.128 1 364.318
# 原 9 股 × 329.128      = 2,962.152
# 新 1 股 × 364.318      = 364.318
# 合計 10 股             = 3,326.470
# 加權均價              = 332.647
```

### 匯率查詢範例

```bash
python3 skills/fx-rates/scripts/fx.py            # 預設 USD/CNY、USD/HKD、HKD/CNY
python3 skills/fx-rates/scripts/fx.py EUR JPY    # 任意幣對
python3 skills/fx-rates/scripts/fx.py all        # 全部主要貨幣
```

---

## 搭配 AI 使用

本倉庫設計為「AI 工作區」。用支援 `AGENTS.md` 的 AI 工具（如 WorkBuddy / CodeBuddy）打開本資料夾，AI 會自動讀取 `AGENTS.md` 的運作規則，你直接說：

- 「分析我的持倉」／「跑一遍」→ 拉報價、算 P&L、掃當天新聞、檢查風險
- 「分析 NVDA」→ 個股深度分析（`us-stock-analysis` 技能）
- 「匯率多少」→ 實時匯率（`fx-rates` 技能）
- 「騰訊 PE 多少」→ 自然語言金融數據查詢

`skills/` 下的技能也可單獨載入到 AI 對話中使用。

---

## 注意事項

- **絕不執行任何交易**：本框架只做分析與提示，不下單、不撤單、不改單。
- **數據來源**：報價優先 CNBC 開放 API；匯率用 er-api（免 key）。Yahoo Finance 在部分雲端環境會被限流，故未採用。
- **漲跌顯示約定**：本倉庫沿用「綠漲紅跌」慣例（綠色 = 上漲 +，紅色 = 下跌 −）。
- **資料同步**：`scripts/quotes.py` 內的持倉字典、`deficit.py` 的 `DEFICITS` 必須與你自己的持倉紀錄保持一致；改持倉先跑 `cost.py` 算均價。
- **隱私**：`DATA/`、`memory/`、持倉紀錄等含個資的檔案請自行加入 `.gitignore`，勿推上公開倉庫（本框架已預設不追蹤這些檔）。
- **可重現性**：所有金額計算都走腳本，禁止在對話中手算，確保精度一致、可審計。
