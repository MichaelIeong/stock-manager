# stock-manager

個人投資組合分析工具——用來追蹤美股、港股、A 股的持倉盈虧、缺口回補進度與預期報酬。

> ⚠️ 本專案**不含任何個人資料**。所有持倉、觀察清單、缺口、計劃都需由你自行填入（見下方「快速上手」）。這是一個「空白模板 + 計算腳本」的框架，clone 下來填你自己的數字即可使用。

---

## 第一步：Clone 這個項目並配好 GitHub SSH Key

### 1. Clone 專案

```bash
git clone git@github.com:MichaelIeong/stock-manager.git
cd stock-manager
```

如果出現 `Permission denied (publickey)` 或 `Could not read from remote repository`，代表你電腦還沒設好 GitHub 的 SSH Key，跟住下面步驟設定。

### 2. 檢查是否已有 SSH Key

```bash
ls ~/.ssh/id_ed25519.pub
```

- 有輸出 → 跳到第 4 步直接把公鑰加到 GitHub。
- 沒有 → 繼續第 3 步產生一對新 Key。

### 3. 產生 SSH Key（如未有）

```bash
ssh-keygen -t ed25519 -C "你的email@example.com"
# 一路按 Enter 用預設值即可（不需設密碼；要密碼保護也可自行設定）
```

### 4. 複製公鑰內容

```bash
# macOS
cat ~/.ssh/id_ed25519.pub | pbcopy     # 自動複製到剪貼板
# 或手動顯示後自行複製：
cat ~/.ssh/id_ed25519.pub
```

### 5. 把公鑰加到 GitHub

1. 登入 GitHub → 右上角頭像 → **Settings**
2. 左側 **SSH and GPG keys** → **New SSH key**
3. Title 隨便填（例如 `My MacBook`），Key type 選 **Authentication Key**
4. 把剛才複製的內容貼到 Key 欄 → **Add SSH key**

### 6. 測試連線

```bash
ssh -T git@github.com
# 看到 "Hi MichaelIeong! You've successfully authenticated..." 即成功
```

### 7. 重新 Clone（或之後正常 push / pull）

```bash
git clone git@github.com:MichaelIeong/stock-manager.git
```

---

## 環境需求

- **Python 3.10+**（腳本只用標準庫，無額外 pip 依賴）
- **curl**（用於拉取報價；macOS / Linux 內建）
- **網絡連線**（報價與匯率來自公開免登入 API）

---

## 目錄結構

```
stock-manager/
├── README.md                      # 本文件
├── scripts/                       # 計算腳本（所有金額都用腳本算，禁止手算）
│   ├── cost.py                    # 加倉後加權平均成本
│   ├── quotes.py                  # 全組合 P&L + 美股 24h 參考價（主力）
│   ├── deficit.py                 # 缺口帳本（單一事實來源）
│   ├── recovery.py                # 缺口回補難度模型（帶每月加倉複利）
│   └── expected_return.py         # 自下而上預期年化報酬模型
├── skills/                        # 選用：可載入 AI 助手做對話式分析（stock-analysis / us-stock-analysis / fx-rates）
└── DATA/                          # （你建立）每日即時報價快照，格式 quotes_YYYY-MM-DD.json
```

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

SYMBOL_NAMES = {            # A 股 / 港股建議加中文名（報表顯示用）
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

> 美股未開盤時，主表「現價」會自動改用盤前／盤後 CNBC 即時價，或 Cboe 24 小時夜間參考價（非昨收），並在「來源」欄標註。

### 3. 計算組合盈虧

```bash
python3 scripts/quotes.py
# 或指定報價檔：
python3 scripts/quotes.py DATA/quotes_2026-08-07.json
```

輸出每檔持倉的現價、成本、市值、盈虧、漲跌%，以及各市場與全組合合計。匯率由腳本自動從 er-api 拉取。

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
| `skills/fx-rates/scripts/fx.py` | 實時匯率（免 key） | `python3 skills/fx-rates/scripts/fx.py [幣種對...\|all]` |

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

## 注意事項

- **絕不執行任何交易**：本工具只做分析與提示，不下單、不撤單、不改單。
- **數據來源**：報價優先 CNBC 開放 API；匯率用 er-api（免 key）。Yahoo Finance 在部分雲端環境會被限流，故未採用。
- **漲跌顯示約定**：本專案沿用「綠漲紅跌」慣例（綠色 = 上漲 +，紅色 = 下跌 −）。
- **資料同步**：`scripts/quotes.py` 內的持倉字典、`deficit.py` 的 `DEFICITS` 必須與你自己的持倉紀錄保持一致；改持倉先跑 `cost.py` 算均價。
- **隱私**：`DATA/`、`memory/`、持倉紀錄等含個資的檔案請自行加入 `.gitignore`，勿推上公開倉庫（本框架已預設不追蹤這些檔）。
- **可重現性**：所有金額計算都走腳本，禁止手算，確保精度一致、可審計。
- **選用 AI 輔助**：本專案附 `AGENTS.md` 與 `skills/`（stock-analysis / us-stock-analysis / fx-rates），可載入 AI 助手做對話式分析；不使用 AI 也能直接跑上面嘅腳本。
