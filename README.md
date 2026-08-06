# stock-manager

AI 輔助的個人投資組合分析框架，透過 AI 助手追蹤美股、港股、A 股的持倉盈虧、缺口回補進度與預期報酬。

> ⚠️ 本專案**不含任何個人資料**。所有持倉、觀察清單、缺口、計劃都需由你自行填入，再交給 AI 助手分析（見下方「填入你的資料」）。

---

## 一、初始化：Clone 並設定 GitHub SSH Key

### 1. Clone 專案

```bash
git clone git@github.com:MichaelIeong/stock-manager.git
cd stock-manager
```

若出現 `Permission denied (publickey)` 或 `Could not read from remote repository`，代表你的電腦尚未設定 GitHub 的 SSH Key，請依照下列步驟設定。

### 2. 檢查是否已有 SSH Key

```bash
ls ~/.ssh/id_ed25519.pub
```

- 有輸出 → 直接跳到第 4 步，將公鑰加入 GitHub。
- 沒有輸出 → 繼續第 3 步，產生一組新的 Key。

### 3. 產生 SSH Key（若尚未擁有）

```bash
ssh-keygen -t ed25519 -C "你的email@example.com"
# 一路按 Enter 使用預設值即可（可不設密碼，亦可自行設定密碼保護）
```

### 4. 複製公鑰內容

```bash
# macOS
cat ~/.ssh/id_ed25519.pub | pbcopy     # 自動複製到剪貼板
# 或手動顯示後自行複製：
cat ~/.ssh/id_ed25519.pub
```

### 5. 將公鑰加入 GitHub

1. 登入 GitHub → 右上角頭像 → **Settings**
2. 左側 **SSH and GPG keys** → **New SSH key**
3. Title 可任意填寫（例如 `My MacBook`），Key type 選擇 **Authentication Key**
4. 將剛才複製的內容貼到 Key 欄 → **Add SSH key**

### 6. 測試連線

```bash
ssh -T git@github.com
# 看到 "Hi 你的帳號! You've successfully authenticated..." 即表示成功
```

---

## 二、建立你自己的倉庫並推送

本專案預設的遠端指向原作者的倉庫，你應該把它指向**你自己的 GitHub 倉庫**，才能保存你的設定與分析紀錄。

### 方式 A：在 GitHub 新建倉庫（推薦）

1. 登入 GitHub，點擊右上角 **＋** → **New repository**
2. 填寫 Repository name（例如 `my-stocks`）
3. **不要**勾選「Add a README file」、「Add .gitignore」、「Choose a license」——因為本專案已經包含這些檔案
4. 點擊 **Create repository**，複製該新倉庫的 SSH 網址（格式為 `git@github.com:你的帳號/你的倉庫.git`）
5. 在本機將遠端改成你自己的倉庫：

```bash
git remote set-url origin git@github.com:你的帳號/你的倉庫.git
```

6. 推送：

```bash
git push -u origin main
```

### 方式 B：Fork 後推送

1. 在本專案頁面點擊 **Fork**，將其複製到你的帳號下
2. 將你 fork 後的倉庫 clone 下來（網址為 `git@github.com:你的帳號/stock-manager.git`）
3. 正常進行後續的 `git add` / `git commit` / `git push` 即可

---

## 三、基本用法：交給 AI 助手

本專案設計為「AI 工作區」，所有實際的分析與計算都由 AI 助手完成，你不需要自己執行腳本。

請使用支援 `AGENTS.md` 的 AI 工具（例如 WorkBuddy、CodeBuddy）開啟本資料夾。AI 會自動讀取 `AGENTS.md` 中的運作規則（報價來源、計算方式、風險檢查清單），你只需告訴它想做什麼：

| 你想做的事 | 對 AI 說 |
|---|---|
| 執行完整分析 | 「分析我的持倉」／「跑一遍」 |
| 研究單一標的 | 「分析 NVDA」／「比較 MSFT 與 GOOGL」 |
| 查詢匯率 | 「匯率多少」 |
| 查詢個股數據 | 「騰訊的 PE 是多少」 |
| 掃描當日新聞與風險 | 「今天有什麼需要注意的」 |

AI 會自動為你：拉取 CNBC 即時報價並存檔、計算完整組合損益、掃描當日新聞、檢查集中度／單一標的虧損／備兌 Call 到期等風險，並給出分析提示（**不會下單**）。

`skills/` 資料夾內亦提供可單獨載入 AI 對話的技能：
- **stock-analysis** — 個股 / 加密貨幣 8 維評分、組合管理、熱門掃描、傳聞探測
- **us-stock-analysis** — 美股深度分析（基本面 / 技術面 / 估值 / 對比）
- **fx-rates** — 即時匯率查詢（免 API key）

---

## 四、填入你的資料（直接截圖給 AI 即可）

你**不需要**自己編輯任何程式碼。AI 助手會根據你的券商 App 或帳單截圖，自動幫你填入持倉資料。

### 步驟

1. 在手機或電腦上開啟你的券商 App（如美股、港股、A 股帳戶的持倉頁面）。
2. **截圖**整個持倉清單（包含標的代號、股數、成本價；若有多個市場請分別截圖）。
3. 在 AI 對話中**直接貼上截圖**，並對 AI 說：

   > 「這是我的持倉截圖，請幫我填入 `scripts/quotes.py` 並分析我的持倉。」

4. AI 會自動讀取圖中的標的、股數、成本價，寫入 `scripts/quotes.py` 的對應常數（美股 `US_POSITIONS`、港股 `HK_POSITIONS`、A 股 `CN_POSITIONS`、`SYMBOL_NAMES` 中文名稱），接著執行分析。

### 截圖小Tips

- 若同一張圖涵蓋多個市場（美股 + 港股 + A 股），請在圖中清楚區分，或分開多張截圖。
- 成本價請確認是「含費用」的實際成本，以利盈虧計算精準。
- 若券商介面以當地貨幣顯示（美股 USD、港股 HKD、A 股 CNY），直接截圖即可，AI 會自行換算。

### 進階：缺口回補

若有需要回補的歷年缺口，同樣把你的紀錄截圖貼給 AI，請它填入 `scripts/deficit.py` 的 `DEFICITS` 清單即可。

> 想要自己動手也可以：常數格式如下（但一般使用者建議直接截圖交給 AI 處理）。

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
SYMBOL_NAMES = {            # A 股 / 港股建議加上中文名稱
    "700.HK": "騰訊控股",
}
CASH_HKD = 0.0
```

---

## 五、注意事項

- **絕不執行任何交易**：本框架只做分析與提示，不下單、不撤單、不改單。
- **資料來源**：報價優先使用 CNBC 開放 API；匯率使用 er-api（均免登入、免 key）。
- **漲跌顯示慣例**：沿用「綠漲紅跌」慣例（綠色代表上漲 ＋，紅色代表下跌 −）。
- **隱私**：`DATA/`、`memory/`、持倉紀錄等含個人資料的檔案請自行加入 `.gitignore`，勿推送到公開倉庫（本框架已預設不追蹤這些檔）。
- **可重現性**：所有金額計算皆由腳本執行，不能手算，以確保精度一致、可審計。
