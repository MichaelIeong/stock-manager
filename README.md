# stock-manager

AI 輔助的個人投資組合分析框架——用 AI 助手追蹤美股、港股、A 股的持倉盈虧、缺口回補進度與預期報酬。

> ⚠️ 本專案**不含任何個人資料**。所有持倉、觀察清單、缺口、計劃都需由你自行填入，再交畀 AI 助手分析（見下方「填入你的資料」）。

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

---

## 用 AI 助手使用這個專案

本專案設計為「AI 工作區」。你唔使自己執行腳本——用支援 `AGENTS.md` 的 AI 工具（如 WorkBuddy / CodeBuddy）打開本資料夾，AI 會自動讀取 `AGENTS.md` 嘅運作規則（報價來源、計算方式、風險檢查清單），直接同佢講你想做咩就得：

| 你想做咩 | 對 AI 講 |
|---|---|
| 跑完整分析 | 「分析我的持倉」／「跑一遍」 |
| 單一標的深研 | 「分析 NVDA」／「比較 MSFT vs GOOGL」 |
| 查匯率 | 「匯率多少」 |
| 查個股數據 | 「騰訊 PE 多少」 |
| 掃當天新聞 / 風險 | 「今日有咩要留意」 |

AI 會自動幫你：拉 CNBC 即時報價存檔、算全組合 P&L、掃當天新聞、檢查集中度／單一標的虧損／備兌 Call 到期等風險，並給出分析提示（**唔會落單**）。

`skills/` 資料夾內亦提供可單獨載入 AI 對話的技能：
- **stock-analysis** — 個股 / 加密貨幣 8 維評分、組合管理、熱門掃描、傳聞探測
- **us-stock-analysis** — 美股深度分析（基本面 / 技術面 / 估值 / 對比）
- **fx-rates** — 實時匯率查詢（免 API key）

---

## 填入你的資料（交畀 AI 前先做）

AI 分析需要你嘅持倉資料。編輯 `scripts/quotes.py` 頂部常數：

```python
US_POSITIONS = {
    "MSFT": {"shares": 10, "cost_usd": 420.50},
}
HK_POSITIONS = {
    "700.HK": {"shares": 100, "cost_hkd": 380.00},
}
CN_POSITIONS = {
    "159781.SZ": {"shares": 5000, "cost_cny": 1.05},
}
SYMBOL_NAMES = {            # A 股 / 港股建議加中文名
    "700.HK": "騰訊控股",
}
CASH_HKD = 0.0
```

- 美股成本欄 `cost_usd`、港股 `cost_hkd`、A 股 `cost_cny`。
- 有缺口要回補嘅話，喺 `scripts/deficit.py` 填 `DEFICITS`。
- 填好之後直接同 AI 講「分析我的持倉」，餘下嘅報價拉取同計算 AI 會搞掂。
- 想自己執行腳本亦可：`python3 scripts/quotes.py`、`scripts/deficit.py`、`scripts/recovery.py`、`scripts/expected_return.py`、`scripts/cost.py`。

---

## 注意事項

- **絕不執行任何交易**：本框架只做分析與提示，不下單、不撤單、不改單。
- **數據來源**：報價優先 CNBC 開放 API；匯率用 er-api（均免登入、免 key）。
- **漲跌顯示約定**：沿用「綠漲紅跌」慣例（綠色 = 上漲 +，紅色 = 下跌 −）。
- **隱私**：`DATA/`、`memory/`、持倉紀錄等含個資檔案請自行加入 `.gitignore`，勿推上公開倉庫（本框架已預設不追蹤呢啲檔）。
- **可重現性**：所有金額計算都走腳本，唔能手算，確保精度一致、可審計。
