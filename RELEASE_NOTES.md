# Dashboard Live Release Notes

## 版本命名規範

- **dashboard_live.py** → 最先使用，不斷修改
- **dashboard_live_v2_x.py** → 重大里程碑備份

### 發布流程
1. 平時修改都在 dashboard_live.py
2. 有重大功能更新或里程碑 → 備份為 dashboard_live_v2_X.py
3. Release Notes 記錄變更

---

## 版本總覽

| 版本 | 檔案 | 大小 | 日期 | 狀態 |
|------|------|------|------|------|
| **v3.0 (最新)** | dashboard_live.py | 19,577 | 2026-04-22 | ✅ 使用中 |
| v2.1 | dashboard_live_v2_1.py | 17,645 | 2026-04-22 | 備份 |
| v2.0 | dashboard_live_1.py | 13,999 | 2026-04-15 | 棄用 |
| v1.0 | dashboard_live_new.py | 8,243 | 2026-04-15 | 棄用 |
| 原版 | dashboard_live_orig.py | 8,243 | 2026-04-15 | 棄用 |

---

## 功能比較

| 功能 | v3.0 | v2.1 | v2.0 | v1.0 |
|------|------|------|------|------|
| 基本技術線圖 | ✅ | ✅ | ✅ | ✅ |
| 法人買賣超 | ✅ | ✅ | ✅ | ✅ |
| 信號選擇 (signal_t86/summary) | ✅ | ✅ | ❌ | ❌ |
| 歷史買點下拉選單 | ✅ | ✅ | ❌ | ❌ |
| 股票中文顯示 | ✅ | ✅ | ❌ | ❌ |
| 指標說明 | ✅ | ✅ | ❌ | ❌ |
| 我的庫存選單 | ✅ | ❌ | ❌ | ❌ |
| 庫存一鍵分析 | ✅ | ❌ | ❌ | ❌ |
| 預設勾選指標 | ✅ (KD/RSI/MACD/Williams) | ❌ | ❌ | ❌ |

### 使用的資料來源
- 股價數據：`/Volumes/AI_Drive/StockData/monthly_data/ohlc_full.csv`
- 股票清單：`/Volumes/AI_Drive/StockData/active_stocks.csv`
- 庫存：`/Volumes/AI_Drive/StockData/my_stocks.csv`
- 信號舊：`/Volumes/AI_Drive/StockData/signals/signal_t86_*.csv`
- 信號新：`/Volumes/AI_Drive/StockData/signals/summary_*.csv`
- 下載腳本：`/Volumes/AI_Drive/StockData/scripts/download_my_stocks_history.py`

---

## v3.0 更新日譜 (2026-04-22)

### 新增功能
- 📦 **我的庫存功能**
  - 讀取 my_stocks.csv
  - Sidebar 新增庫存選單
  - 點選直接分析該股票
- 📊 **信號來源選擇**
  - radio button 選擇 signal_t86 或 summary
  - 各自獨立的日期下拉選單
  - 顯示說明文字
- 🏷️ **股票中文顯示**
  - 標題顯示「股票名稱 (代碼)」
  - 從 active_stocks.csv 查詢
- 📖 **指標說明**
  - 各指標買點顯示判斷條件
  - KD/RSI/MACD/Williams 等
- ⚙️ **預設指標**
  - 預設勾選 KD, RSI, MACD, Williams

### 修復
- 修復 summary 格式相容性（name, signals 欄位）
- 修復 price 欄位不存在錯誤
- 修復日期下拉選單重複問題
- 修復股票代碼與名稱對應

---

## v2.1 更新日誌 (2026-04-22)

### 使用的資料來源
- 股價數據：`/Volumes/AI_Drive/StockData/monthly_data/ohlc_full.csv`
- 股票清單：`/Volumes/AI_Drive/StockData/active_stocks.csv`
- 信號舊：`/Volumes/AI_Drive/StockData/signals/signal_t86_*.csv`
- 信號新：`/Volumes/AI_Drive/StockData/signals/summary_*.csv`

### 新增功能
- 信號來源選擇 (signal_t86/summary)
- 歷史買點下拉選單（最近10個檔案）
- 股票中文顯示
- 指標說明

### 差異 vs v2.0
- 沒有我的庫存功能
- 其他與 v3.0 相同

---

## v2.0 更新日誌 (2026-04-15)

### 使用的資料來源
- 股價數據：`/Volumes/AI_Drive/StockData/monthly_data/ohlc_full.csv`
- 股票清單：`/Volumes/AI_Drive/StockData/active_stocks.csv`
- 信號舊：`/Volumes/AI_Drive/StockData/signals/signal_t86_*.csv`

### 基礎版本
- 基本技術線圖
- 法人買賣超
- signal_t86 歷史買點
- 多指標獨立買點訊號

---

## 技術細節

### 資料來源
- 股價數據：`/Volumes/AI_Drive/StockData/monthly_data/ohlc_full.csv`
- 股票清單：`/Volumes/AI_Drive/StockData/active_stocks.csv`
- 庫存：`/Volumes/AI_Drive/StockData/my_stocks.csv`
- 信號：`/Volumes/AI_Drive/StockData/signals/signal_t86_*.csv`
- 新信號：`/Volumes/AI_Drive/StockData/signals/summary_*.csv`

### 股票代碼格式
- 一般股票：4碼數字 (如 2317, 2330)
- ETF：5碼 (如 00713, 00878)
- 注意：Yahoo Finance 需要加 .TW 後綴

---

## 執行方式

```bash
# 啟動服務
cd /Volumes/AI_Drive/StockData/scripts
python3 -m streamlit run dashboard_live.py --server.port 8503 --server.headless true

# 停止服務
pkill -f dashboard_live
```

---

## 未來規劃
- [ ] 支援更多資料來源
- [ ] 機器人自動提醒
- [ ] 庫存歷史資料自動下載
- [ ] 買賣訊號推送到 Discord

---

## 相關腳本檔案

| 腳本 | 用途 |
|------|------|
| download_my_stocks_history.py | 下載庫存歷史資料 |
| t86_fetch_all.py | 抓取法人買賣超資料 |
| signal_summary.py | 產生買點訊號 |
| daily_update.py | 每日資料更新 |

---

## 資料櫃結構

```
/Volumes/AI_Drive/StockData/
├── active_stocks.csv         # 股票清單
├── my_stocks.csv             # 我的庫存
├── monthly_data/
│   └── ohlc_full.csv        # 股價歷史
├── signals/
│   ├── signal_t86_*.csv     # 舊買點訊號
│   └── summary_*.csv        # 新買點訊號
├── scripts/
│   ├── dashboard_live.py   # 使用中
│   ├── download_my_stocks_history.py
│   ├── t86_fetch_all.py
│   └── signal_summary.py
└── RELEASE_NOTES.md
```

---

## 買點資料格式

### 1. signal_t86_* (舊格式)
- 來源：法人買賣超 T86 資料
- 欄位：
  - code, price, signals, count, RSI, Williams, total_net, recommendation
- 產生方式：RD 的 script (t86_fetch_all.py 或類似)
- 判斷邏輯：
  - RSI < 30 → 信號
  - Williams < -50 → 信號
  - MACD > signal → 信號
  - MA200 上 → 信號
  - 法人買賣超

### 2. summary_* (新格式)
- 來源：趨勢確認
- 欄位：
  - rank, code, name, date, signals, signal_count, RSI, Williams, recommendation
- 產生方式：signal_summary.py
- 判斷邏輯：
  - RSI 從 <30 回升到 >=30 → 信號
  - Williams 從 <-80 回升到 >=-80 → 信號
  - MACD 金叉且 > 0 → 信號
  - 法人買賣超

---

## 庫存相關

### my_stocks.csv 格式
```csv
code,name,avg_volume,last_updated
2330,台積電,37138,20260422
2317,鴻海,59414,20260422
00713,元大台灣高息低波,0,20260422
```

### 如何更新
1. 更新 Google Doc：https://docs.google.com/document/d/1T9SWbc_vJTKx4AlydEd_q44i1-KXa8tFYVJeHzDQehs/edit
2. 告訴 Ass「更新庫存」
3. Ass 會：
   - 抓 Google Doc → my_stocks.csv
   - 同步到 active_stocks.csv
   - 下載歷史資料 (download_my_stocks_history.py)

---

## 更新流程圖

```
老闆更新 Google Doc
    ↓
說「更新庫存」
    ↓
Ass 抓取 → my_stocks.csv
    ↓
同步 → active_stocks.csv
    ↓
下載歷史 → ohlc_full.csv
    ↓
產生買點 → signal_t86_*.csv / summary_*.csv
```

---

## v1.01 Stock Strategy 更新日誌 (2026-04-22 補推)

### 新增腳本

| 腳本 | 用途 |
|------|------|
| nightly_stock_v1_01.sh | 每夜自動跑策略生成 + 回測 |
| make_stock_strategy_v1_01.py | 根據 deepseek 給的規則動態生成策略程式 |

### nightly_stock_v1_01.sh 功能
- 呼叫 deepseek API 取得成功規則（RULE）
- 動態生成 stock_strategy_v1_01.py
- 回測指定股票（0056.TW）
- 產出 runs.jsonl + summary.md
- 記錄每日 proposal 到 `/Volumes/AI_Drive/AI_Workspace/openclaw_design/stock_strategy/v1.01/proposals/`

### 依賴
- Python venv: `~/.venv/bin/python`
- 資料路徑: `/Volumes/AI_Drive/StockData/`
- AI API: deepseek v1_01 success rule

### 使用方式
```bash
# 手動執行
bash nightly_stock_v1_01.sh

# 或設定 cron 自動跑
0 2 * * * cd /Users/jues/.openclaw/dashboard-stock && ./nightly_stock_v1_01.sh >> /tmp/stock_nightly.log 2>&1
```


---

## v2.2 更新日誌 (2026-04-22)

### 版本狀態
- 與 v3.0 (`dashboard_live.py`) 相同
- 大小：19,577 bytes
- 日期：2026-04-22 14:17

### 主要功能
- 📦 我的庫存功能
- 📊 信號來源選擇 (signal_t86/summary)
- 🏷️ 股票中文顯示
- 📖 指標說明
- ⚙️ 預設指標 (KD/RSI/MACD/Williams)

