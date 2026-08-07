# AGENTS.MD — 金融投資組合分析工作區

> 本文件為此工作區的「常駐運作手冊」。AI 每次進入此空間時，應先閱讀並遵循本文。

## 項目背景與適用範圍

本工作區並非程式碼專案，而是一個**以 AI 輔助的個人金融投資組合分析空間**。適用範圍包含：

- **觀察清單**：追蹤指定美股、港股標的的實時報價與當天新聞。
- **持倉管理**：記錄現有持倉結構，僅存標的／數量／成本價／備兌結構，**不固化現價與盈虧**，所有動態數值由 skill 實時計算。
- **資金計劃**：新增資金配置規劃、目標 ETF 選擇與預算（詳見 `plan.md`）。
- **資產配置研究**：針對新增資金進行 ETF 選擇、跨市場配置、風格分散討論。
- **風險與再平衡提示**：分析時自動檢查集中度、單一標的虧損、備兌 Call 到期等風險，但不執行任何交易。

## 核心資源與技能

AI 在此工作區優先使用以下技能與數據源：

| 技能 | 用途 | 觸發 |
|---|---|---|
| `stock-analysis` | CNBC 報價 + 新聞掃描 + `scripts/quotes.py` 算 P&L | 「分析我的清單」「跑一遍」 |
| `us-stock-analysis` | 美股深度分析（基本面/技術面/估值/對比），含盤前盤後 | 「分析 NVDA」「比較 MSFT vs GOOGL」 |
| `westock-data` | **技術面點位專用**：騰訊自選股公開接口（免登入、免 key、不生成 HTML），涵蓋美股/港股/A股 的 K線、技術指標（MA/MACD/KDJ/RSI/BOLL/BIAS/WR/DMI）、籌碼。CLI：`npx -y westock-data-clawhub@1.0.4 technical <code> --group ma,macd,rsi,boll,kdj`；代碼格式 `usNVDA`/`hk00700`/`sz159781` | 「分析點位」「技術面」「支撐阻力」 |
| `neodata-financial-search` | 自然語言金融數據（A 股/港股/美股/宏觀） | 「騰訊 PE 多少」 |
| `fx-rates` | 實時匯率（USD/CNY/HKD），er-api 免 key | 「匯率多少」 |
| `wb-finance-skill` | 金融場景總入口，協調上述 skill | — |

技能原始檔在 `skills/`（已納入 Git）。Yahoo Finance 在沙箱被限流，報價改用 CNBC API。

數據原則：

- **優先免登入、免 API key 的數據源。**
- 報價、盈虧、市值等動態數值**每次分析時實時拉取**，不固化進 `positions.md`。
- **每日拉取之現價快照統一備份至 `DATA/` 資料夾存檔**。
- 若即時數據不可用（如 IP 限流），明確告知用戶並建議本機執行替代方案。

## 現價拉取與存檔方法（CNBC 開放 API，免登入免 key）

經實測，以下為本工作區**唯一穩定可用**的即時報價來源：沙箱 bash 直連可達，無需登入或 API key，亦不被限流。

### 指令與存檔

每日執行分析或拉取報價時，使用 `curl` 將報價 JSON 儲存至 `DATA/` 資料夾：

```bash
curl -sS -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=<你的代碼，例如 AAPL|MSFT|0700.HK>&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&_=$(date +%s%N)" > "DATA/quotes_$(date +%Y-%m-%d).json"
```

> ⚠️ **CNBC CDN 快取陷阱**：短時間內重複請求同一 URL，CNBC 會回傳**別的請求的快取回應**（例如多出 VTV / 510300.SS、缺了你要拉的代碼）。解法：每次 URL 加 `&_=$(date +%s%N)` 破快取；拉完立即用 `python3 -c "import json;d=json.load(open('DATA/quotes_$(date +%Y-%m-%d).json'));print([q['symbol'] for q in d['FormattedQuoteResult']['FormattedQuote']])"` 驗證標的齊全。另：勿在 `DATA/` 放 `quotes_latest.json` 之類非日期命名檔，`scripts/quotes.py` 的 `find_latest_quotes()` 已限定只認 `quotes_YYYY-MM-DD.json`。

### 要點

- **多標的**：用 `|`（pipe）串接，如 `AAPL|MSFT|0700.HK`。
- **市場代碼**：美股直接寫代號（例：`AAPL`）；港股加 `.HK` 後綴（例：`0700.HK`，**不要加前綴 0**，`scripts/quotes.py` 的 `norm_hk()` 會自動去前導零）；A 股加 `.SS`（上海）／`.SZ`（深圳）後綴（例：`159781.SZ`）。
- **回傳結構**：`FormattedQuoteResult.FormattedQuote[]`，每檔欄位：
  - `symbol`、`last`（最新價）、`change`、`change_pct`（漲跌%）
  - `previous_day_closing`（昨收）、`currencyCode`（幣種）
  - `curmktstatus`（市場狀態：PRE / REG / POST / CLOSED）、`realTime`、`last_timedate`（時點）
- **盤前／盤後**：`exthrs=1` 已開啟；`last` 多數情況為常規收盤，美股盤前價需結合 `curmktstatus=PRE` 與 `change_pct` 輔助判讀。
- **漲跌顏色**：**依用戶明確指示，漲跌顯示規則為綠漲紅跌（綠色表示上漲 +、紅色表示下跌 -）。**

### 24 小時／夜間參考價（Cboe 延時報價，免 key）

美股交易所**無真正 24 小時交易**：盤前 04:00–09:30 ET、常規 09:30–16:00 ET、盤後 16:00–20:00 ET；深夜 20:00–04:00 ET 僅部分券商 overnight ATS（Blue Ocean 等）。為滿足「任何時段都要有參考價」，加入 **Cboe 延時報價**（實測免 key 可用）：

```bash
curl -sS --insecure -A "Mozilla/5.0" "https://cdn.cboe.com/api/global/delayed_quotes/quotes/{SYMBOL}.json"
```

- 回傳 `data.current_price`／`bid`／`ask`／`timestamp`（美東）；**夜間仍會更新**（延遲約 15 分鐘，非成交價）。
- CNBC 深夜會停留在 `POST_MKT_PREV`（前一晚盤後舊數據），此時以 Cboe 價為夜間參考。
- 沙箱時鐘偏離會令 SSL 驗證失敗，須加 `--insecure`。
- 美股未開盤（盤前/盤後/休市）時，`scripts/quotes.py` 主表「現價」自動改用盤前/盤後 CNBC 即時價或 Cboe 24h 夜間參考價（**非昨收**），並於「來源」列標註；底部「🌙 24h 參考價細節」區塊列出 Cboe bid/ask 對照。常規交易時段才顯示收盤（即時成交）價。核心函數 `us_live_price(sym, q, usd_hkd)` 已抽離，`expected_return.py` 共用。

### 已實測失敗、勿再浪費時間的來源

| 來源 | 結果 | 原因 |
|---|---|---|
| Yahoo v8 chart API（`query1/query2.finance.yahoo.com/v8/...`） | HTTP 429 | 雲端沙箱 IP 被 Yahoo 限流（`Edge: Too Many Requests`） |
| Yahoo v7 quote API（bash 或 WebFetch） | HTTP 401 | 該端點現已要求登入授權 |
| Stooq CSV（`stooq.com/q/...`） | 機器人 PoW 牆 | 需 SHA-256 驗證，curl 無法通過 |

> 若 CNBC 亦偶發失敗，明確告知用戶並改用本機執行替代方案，切勿編造數據。

## 工作區關鍵檔案

| 檔案／目錄 | 用途 |
|---|---|
| `watchlist.md` | 觀察清單（美股 + 港股 + A 股），含代碼與備註 |
| `positions.md` | 持倉紀錄，**只記標的／數量／成本價／結構**，不寫現價／盈虧 |
| `plan.md` | 資金計劃（記錄新增資金配置、目標 ETF 選擇與預算分配；含每月工資提撥節奏） |
| `deficits.md` | 歷年期權/FRCB 炒作缺口賬本與回補進度（用戶已戒賭，純紀錄） |
| `DATA/` | 每日實時拉取的現價備份資料夾（檔名格式：`quotes_YYYY-MM-DD.json`） |
| `memory/MEMORY.md` | 專案長期記憶（僅留存補充性記憶，避免與 AGENTS.MD 重複） |
| `memory/YYYY-MM-DD.md` | 每日工作日誌（append-only） |

| `scripts/` | Python 工具腳本（成本計算、組合盈虧） |

### Python 腳本（強制規則）

⚠️ **所有數學計算（成本均價、持倉盈虧、匯率換算等）必須使用 Python 腳本，禁止心算或 bash 算術。** 確保精度一致、可重現、可審計。

| 腳本 | 用途 | 用法 |
|---|---|---|
| `scripts/cost.py` | 加倉後加權平均成本計算 | `python3 scripts/cost.py <舊股數> <舊均價> <新股數> <新成交價>` |
| `scripts/quotes.py` | 全組合 P&L＋已實現獲利＋美股 24h 參考價（未開盤時主表現價自動用盤前/盤後 CNBC 或 Cboe 夜間價，並標「來源」列）；`us_live_price()` 統一美股現價邏輯；`SYMBOL_NAMES` / `sym_name()` 提供標的中文名稱；`REALIZED_GAINS` / `CALL_PREMIUM_HKD` 須與 positions.md 同步 | `python3 scripts/quotes.py [quotes_json_path]` |
| `scripts/deficit.py` | 缺口帳本**單一事實來源**（歷年缺口／年終目標／回補進度）；`quotes.py` 由此 import 目標數字 | `python3 scripts/deficit.py [投資收益]` |
| `scripts/recovery.py` | 回補難度模型（**帶每月加倉**）：月度迭代複利＋二分法逆解所需報酬率、正推各年化情境收益與達標月數 | `python3 scripts/recovery.py [--capital N] [--monthly N] [--months N] [--cash N]` |
| `scripts/expected_return.py` | 自下而上預期年化報酬模型：逐檔估值（EPS×PE / P/S / 券商目標價），三情境機率加權，貢獻度分析，缺口回補映射；**美股現價同採 `us_live_price()`（未開盤用盤前/Cboe 即時價）** | `python3 scripts/expected_return.py [quotes_path] [--scenario bear|base|bull] [--deploy-cash]` |
| `scripts/live_server.py` | 即時組合報價儀表板：本地 HTTP 伺服器（端口 8999），CNBC 即時價＋自動刷新（30 秒），逐檔 P&L、今日盈虧、綠漲紅跌 | `python3 scripts/live_server.py [--port PORT]` → `http://localhost:PORT` |

#### 成本計算規則
- 每次用戶調倉（加倉／減倉），先用 `scripts/cost.py` 算出新的加權均價，再更新 `positions.md`。
- `scripts/quotes.py` 中的持倉成本字典（`US_POSITIONS` / `HK_POSITIONS` / `CN_POSITIONS`）須與 `positions.md` 保持同步；已實現獲利字典 `REALIZED_GAINS` 與 `CALL_PREMIUM_HKD`（備兌 Call 權利金，由用戶提供金額）亦須同步。
- **缺口數字只改 `scripts/deficit.py`**（`DEFICITS` 清單），`deficits.md` 為人讀鏡像；年終目標（一半基準／硬下限）由腳本自動計算，禁止在其他檔案硬編碼。
- **回補難度／所需報酬率一律用 `scripts/recovery.py`**：用戶每月加倉，本金逐月變大，**嚴禁用固定本金 × 百分比手算**。新錢只賺到剩餘月份，須用月度迭代模型；`--capital` 預設值須跟 `quotes.py` 最新組合總值同步。
- **回補進度用基準線制**：`deficit.py` 的 `BASELINE_INCOME`（基準日投資收益）已內含於缺口，故**淨回補額 = 當前投資收益 − BASELINE_INCOME**，進度由 0 起計，切勿把基準日當時的盈利重複當成回補。
- **已實現收益記帳格式**：期權／交易類一律記「毛額 − 交易費 = 淨額」，**淨額**才計入回補進度（例：某 covered Call 權利金毛額 1,000 − 費 50 = 淨額 950）。

#### 組合盈虧計算規則
- 每日分析時，先用 CNBC API 拉取報價存檔至 `DATA/`，再執行 `python3 scripts/quotes.py` 輸出完整 P&L 表格。
- 若 `scripts/quotes.py` 中成本與 `positions.md` 不一致，以 `positions.md` 為準並同步更新腳本。

### 持倉檔慣例（用戶明確要求）

`positions.md` 的結構：

- ✅ 記錄：名稱、代碼、數量、成本價、備兌 Call 履約價與到期日。
- ❌ **絕對不寫**：現價、市值、持倉盈虧、今日盈虧。
- 動態數值在每次完整分析時用 skill **實時拉取計算**，並存檔至 `DATA/`，結果僅存在當次分析報告中，不回填到 `positions.md`。

### 持倉更新方式（用戶截圖，AI 填寫）

本專案為 AI 運作工作區，**持倉一律由用戶提供券商 App / 帳單截圖，再由 AI 讀圖後寫入**，用戶無須手動編輯腳本。流程：

1. 用戶在對話中貼上持倉截圖（含標的代號、股數、成本價；多市場請分開截圖），並說明「幫我更新持倉」。
2. AI 讀取圖中標的，轉寫為 `scripts/quotes.py` 的對應常數：
   - 美股 → `US_POSITIONS`（欄位 `shares` / `cost_usd`）
   - 港股 → `HK_POSITIONS`（欄位 `shares` / `cost_hkd`）
   - A 股 → `CN_POSITIONS`（欄位 `shares` / `cost_cny`）
   - `SYMBOL_NAMES` 補齊 A 股 / 港股中文名稱（如 `"700.HK": "騰訊控股"`）
   - 備兌 Call 結構（履約價 / 到期日）一併記入。
3. 同步更新 `positions.md`（僅記標的／數量／成本價／結構，不寫現價盈虧）。
4. 缺口回補：用戶貼缺口紀錄截圖 → AI 寫入 `scripts/deficit.py` 的 `DEFICITS` 清單。
5. 改動後即對用戶確認所寫入的標的、股數、成本價，再執行分析。

> 用戶亦可手動修改 `positions.md` / `watchlist.md` / `plan.md`；AI 在每次分析前應先讀取這些檔案再動作。

## 每次分析時的自動檢查清單

當用戶指示「分析我的清單」或「跑一遍」時，AI 必須完成以下步驟：

1. **報價拉取與存檔**：優先使用 CNBC 即時報價 API 拉取全倉報價，並自動存檔至 `DATA/quotes_YYYY-MM-DD.json`；輸出須含**今日盈虧**（日界 UTC+8 04:00，詳見用戶固定偏好）。
2. **當天新聞**：對觀察清單全標的搜尋當天重要新聞與催化事件。
3. **技術面點位分析（與新聞並重）**：對持倉標的（美股/港股/A股）調用 `westock-data` 拉取技術指標，解讀**趨勢、支撐/阻力、超買超賣、金叉死叉**：
   - **報告順序**：**先給文字「點位解讀」（分市場敘述趨勢、關鍵支撐/阻力位、超買超賣、金叉死叉），再附技術指標原始表格**。文字解讀須在前，表格在後，勿把解讀埋在最後一欄。
   - 指令：`npx -y westock-data-clawhub@1.0.4 technical <code> --group ma,macd,rsi,boll,kdj`（批次可用逗號分隔多碼）。
   - 代碼格式：美股 `usXXXX`、港股 `hkXXXXX`、A股 `sh/szXXXXXX`；ETF 與部分海外個股可能無數據，標註略過。
   - 解讀重點：價格相對 MA（多空排列）、MACD 柱正負（動能）、KDJ/RSI（超買>70 / 超賣<30）、BOLL 上中下軌（支撐阻力區）。
   - 與新聞面交叉驗證（例：技術轉弱＋利空新聞＝減持警戒）。
4. **持倉與計劃檢查**：
   - 單一標的虧損比例是否過大。
   - 科技／行業集中度（特別是個別持倉的主題重疊風險（例如同一產業鏈的多檔持倉））。
   - 備兌 Call 到期日與 cover 狀態。
   - 匯率影響（成本以 HKD 計，但美股為美元資產）。
   - 對照 `plan.md` 資金計劃執行進度與擬加倉標的。
5. **僅提供分析提示，絕不下單或執行交易**。

## 用戶固定偏好與背景

- 語言：所有回覆使用**繁體中文**。
- **漲跌顯示**：**綠漲紅跌（綠色代表上漲、紅色代表下跌）。**
- **全倉報價須含「今日盈虧」**：每次顯示全倉／持倉報價（含 `scripts/quotes.py` 輸出與對話文字摘要）都必須附上**今日盈虧**欄；計算＝（現價 − 昨收）× 股數，日界為 **UTC+8 04:00**（＝美東 16:00 收盤，即美股昨收更新點；港股／A 股昨收為本地收盤）；美股盤後時段「今日盈虧」含盤後價。實作見 `scripts/quotes.py`。
- **幣種顯示**：各市場以「當地貨幣」為主標，旁括號附 HKD 約當現價：
  - 美股 → 以 **USD** 標示（括號附 HKD），例：`AAPL $150.00（≈HK$1,176）`
  - 港股 → 以 **HKD** 標示，例：`0700.HK HK$480.00`
  - A 股 → 以 **CNY** 標示（括號附 HKD），例：`159781.SZ ¥1.10（≈HK$1.28）`
  - 匯率統一由 `scripts/fx-rates/scripts/fx.py` 實時拉取，不寫死。
  - **標的名稱顯示**：分析報表（對話文字與 `scripts/*.py` 輸出）中，**A 股與港股標的除代碼外必須附中文名稱**，例如 `2800.HK 盈富基金（港股寬基ETF）`、`159781.SZ 科創創業50ETF（A股成長ETF）`。美股代碼較直觀可加可不加，但建議一併加強一致性（例如 MSFT 微軟、GOOGL 谷歌）。名稱映射集中於 `scripts/quotes.py` 的 `SYMBOL_NAMES` 常數，腳本經 `sym_name()` 自動正規化港股前導零（令 `0700.HK` 與 `700.HK` 都命中）；**新增標的時必須同步更新 `SYMBOL_NAMES`**。
- 資產結構：可自行在 `plan.md` 記錄定存／股票倉位比例（本框架不含預設配置）。
- 持有期限：事件型倉位（例如某催化事件前後）可定中短期；核心持倉（如大型科技股）可定中長線——請按你自己的持倉填寫。
- 風格與資金計劃：配置建議偏好簡潔方案（2–3 檔 ETF），詳細配置請見 `plan.md`。

## 風險控制與禁止事項

| 禁止項 | 說明 |
|---|---|
| **交易操作** | 絕不執行任何下單、撤單、改單。 |
| **修改持倉檔中的現價** | 持倉檔不得出現現價、市值、盈虧欄位。 |
| **編造數據** | 所有金融數據必須來自 skill 實時查詢，標注來源與時點。 |
| **跨檔案污染** | 不將工作區檔案散落到家目錄、桌面或其他非工作區路徑。 |
| **HTML 報告** | 用戶已要求「不用再做 HTML」，分析結果以對話文字為主。 |

## 協作補充說明

- 若用戶手動修改了 `watchlist.md`、`positions.md` 或 `plan.md`，AI 應先讀取再分析。
- 每日工作日誌為 `append-only`，不可改寫舊內容。
- AI 在每次對話結束前應檢查：是否已將當天報價存至 `DATA/`，是否已更新記憶（`memory/`），是否已寫入今日日誌。
- 如有任何不確定，**必須先問用戶確證**，而非自行推測。

## 版本控制（Git）維護慣例

本工作區已初始化為 Git 倉庫，分支為 `main`，需**持續維護與更新**。請將遠端指向**你自己的倉庫**（教學見 `README.md`）。

### 倉庫結構約定
- **納入版本控制**：`AGENTS.md`、`README.md`、`.gitignore`、`positions.md`、`watchlist.md`、`plan.md`、`DATA/`（每日報價快照）、`memory/`（專案日誌）等專案內容。
- **排除（已在 `.gitignore`）**：`.workbuddy/`（agent 內部記憶與運行檔）、`.DS_Store`。
- ⚠️ **公開前務必自查**：確認無真實持倉、現金餘額、帳戶號碼、API key 等個人資料被誤加入（本框架所有持倉均為空白模板，填寫你的資料後請自行判斷是否適合公開）。

### 持續更新流程
當工作區發生以下變動時，AI 應主動提交並推送，保持遠端倉庫與本地同步：
1. 持倉異動：用戶修改 `positions.md` / `watchlist.md` / `plan.md` 後。
2. 分析產出：完成一次完整分析、寫入當日報價 `DATA/quotes_YYYY-MM-DD.json` 或更新 `memory/` 日誌後。
3. 手冊變更：本 `AGENTS.md` 或專案設定被更新後。

### 提交與推送指令
```bash
cd <你的專案路徑>
git add -A
git commit -m "YYYY-MM-DD: <變動摘要>"
git push origin main
```

### 注意事項
- 提交訊息以**繁體中文**撰寫，前綴當日日期。
- 推送前確認無敏感憑證（API key、密碼）被誤加入；`.workbuddy/` 已透過 `.gitignore` 排除。
- 若 `git push` 失敗，明確告知用戶原因（如遠端權限、衝突、網路），不自行強制覆寫（`--force`）。

---

_本文件最後更新：2026-08-07。由 AI 根據用戶指示與對話歷史生成。_
