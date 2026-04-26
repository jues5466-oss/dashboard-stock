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
| **v2.3 (最新)** | dashboard_live.py | ~24KB | 2026-04-27 | ✅ 使用中 |
| v2.2 | dashboard_live_v2_2.py | 19,577 | 2026-04-22 | 備份 |
| v2.1 | dashboard_live_v2_1.py | 17,645 | 2026-04-22 | 棄用 |
| v2.0 | dashboard_live_1.py | 13,999 | 2026-04-15 | 棄用 |
| v1.0 | dashboard_live_new.py | 8,243 | 2026-04-15 | 棄用 |

---

## 功能比較

| 功能 | v2.3 | v2.2 | v2.1 | v2.0 |
|------|------|------|------|------|
| 基本技術線圖 | ✅ | ✅ | ✅ | ✅ |
| 法人買賣超 | ✅ | ✅ | ✅ | ✅ |
| 信號選擇 (signal_t86/summary) | ✅ | ✅ | ✅ | ❌ |
| 歷史買點下拉選單 | ✅ | ✅ | ✅ | ❌ |
| 股票中文顯示 | ✅ | ✅ | ✅ | ❌ |
| 指標說明 | ✅ | ✅ | ✅ | ❌ |
| 我的庫存選單 | ✅ | ✅ | ❌ | ❌ |
| 庫存一鍵分析 | ✅ | ✅ | ❌ | ❌ |
| 預設勾選指標 | ✅ | ✅ | ❌ | ❌ |
| **DMI 指標** | ✅ | ❌ | ❌ | ❌ |
| **K線型態標記** | ✅ | ❌ | ❌ | ❌ |
| **成交量子圖 (MA5)** | ✅ | ❌ | ❌ | ❌ |
| **效能優化 (快取)** | ✅ | ❌ | ❌ | ❌ |

### 使用的資料來源
- 股價數據：`/Volumes/AI_Drive/StockData_v2/data/daily_data/`
- 股票清單：`/Volumes/AI_Drive/StockData_v2/data/active_stocks.csv`
- 庫存：`/Volumes/AI_Drive/StockData_v2/data/my_stocks.csv`
- 信號舊：`/Volumes/AI_Drive/StockData_v2/data/signals/signal_t86_*.csv`
- 信號新：`/Volumes/AI_Drive/StockData_v2/data/signals/summary_*.csv`

---

## v2.3 更新日誌 (2026-04-27)

### 新增功能
- 📊 **DMI 趨勢指標**
  - ADX 線（平滑趨勢強度）
  - +DI / -DI 趨勢方向
  - 紫色 checkbox (`#C27B0`) 獨立控制
- 🕯️ **K線型態標記**
  - 自動辨識：锤子線 (Hammer)、吞噬形態 (Engulfing)、晨星/夜星 (Morning/Evening Star)、十字星 (Doji)
  - ▲ 綠色標記 = 買入型態
  - ▼ 紅色標記 = 賣出型態
  - 獨立 checkbox 控制（預設關閉）
- 📈 **成交量子圖**
  - K線圖下方新增成交量圖
  - MA5 成交量均線
  - 自動適應 3-row 圖表佈局
- ⚡ **效能優化**
  - 日期索引快取 (`@st.cache_data(ttl=3600)`)
  - Smart date filtering 減少載入資料量
  - 函式級快取 (`@st.cache_data(ttl=300)`)

### 修復
- `indicators` 參數未傳入 `plot_chart()` 問題
- `basename.isdigit()` 錯誤 → 需 `.replace('.csv', '')`
- MA200 使用錯誤欄位名 `prev['Close']` → `prev['close']`
- 全關指標時 K線消失問題 → K線永遠顯示
- `date` 作為 index 時搜尋不到的問題

### 技術細節
- 圖表佈局：`row_heights=[0.5, 0.25, 0.25]`（K線 50%, 技術指標 25%, 成交量 25%）
- K線型態標記用戶可控，預設隱藏
- DMI 計算：ADX 週期 14，標準 DMI 公式

---

## v2.2 更新日誌 (2026-04-22)

### 版本狀態
- 與 v2.3 (`dashboard_live.py`) 相同架構
- 大小：19,577 bytes
- 日期：2026-04-22 14:17

### 主要功能
- 📦 我的庫存功能
- 📊 信號來源選擇 (signal_t86/summary)
- 🏷️ 股票中文顯示
- 📖 指標說明
- ⚙️ 預設指標 (KD/RSI/MACD/Williams)

---

## v2.1 更新日誌 (2026-04-22)

### 新增功能
- 信號來源選擇 (signal_t86/summary)
- 歷史買點下拉選單（最近10個檔案）
- 股票中文顯示
- 指標說明

### 差異 vs v2.0
- 沒有我的庫存功能
- 其他與 v2.2 相同

---

## v2.0 更新日誌 (2026-04-15)

### 基礎版本
- 基本技術線圖
- 法人買賣超
- signal_t86 歷史買點
- 多指標獨立買點訊號

---

## 技術細節

### 資料來源
- 股價數據：`/Volumes/AI_Drive/StockData_v2/data/daily_data/YYYY/MMDD.csv`
- 股票清單：`/Volumes/AI_Drive/StockData_v2/data/active_stocks.csv`
- 庫存：`/Volumes/AI_Drive/StockData_v2/data/my_stocks.csv`
- 信號：`/Volumes/AI_Drive/StockData_v2/data/signals/signal_t86_*.csv`
- 新信號：`/Volumes/AI_Drive/StockData_v2/data/signals/summary_*.csv`

### 股票代碼格式
- 上市股票：`.TW`（如 2330.TW）
- 上櫃股票：`.TWO`（如 3324.TWO）
- ETF：5碼（如 00713, 00878）

---

## 執行方式

```bash
# 啟動服務
cd /Volumes/AI_Drive/StockData_v2/scripts
python3 -m streamlit run dashboard_live.py --server.port 8503 --server.headless true

# 停止服務
pkill -f dashboard_live
```

**Dashboard 網址：** `http://localhost:8503`

---

## 未來規劃
- [ ] 支援更多資料來源
- [ ] 機器人自動提醒
- [ ] 庫存歷史資料自動下載
- [ ] 買賣訊號推送到 Discord/Telegram

---

## 相關腳本檔案

| 腳本 | 用途 |
|------|------|
| daily_update.py | 每日股價 + T86 更新 |
| signal_with_t86.py | 法人買賣超訊號分析 |
| signal_summary.py | 買點訊號摘要 |
| download_my_stocks_history.py | 庫存股歷史回補 |
| backfill_history.py | 歷史股價回補 |
| backfill_t86.py | T86 歷史回補 |

---

## 資料櫃結構

```
StockData_v2/
├── scripts/
│   ├── dashboard_live.py      # ✅ 使用中
│   ├── daily_update.py        # 每日更新
│   ├── signal_with_t86.py     # 法人訊號
│   ├── signal_summary.py       # 買點摘要
│   ├── download_my_stocks_history.py
│   ├── backfill_history.py
│   └── backfill_t86.py
├── data/
│   ├── daily_data/            # 每日一檔（核心）
│   │   └── YYYY/MMDD.csv
│   ├── signals/               # 訊號輸出
│   │   ├── summary_YYYYMMDD.csv
│   │   └── signal_t86_YYYYMMDD.csv
│   ├── active_stocks.csv      # 370 檔追蹤清單
│   ├── my_stocks.csv          # 個人庫存
│   └── excluded_stocks.csv    # 排除清單
├── logs/
│   ├── signal.log
│   └── signal_t86.log
├── RELEASE_NOTES.md
├── README.md
└── stock-dashboard-v2-doc.md
```

---

## 日檔格式（`data/daily_data/YYYY/MMDD.csv`）

| 欄位 | 說明 |
|------|------|
| `date` | 日期（YYYYMMDD） |
| `code` | 股票代碼（str，4碼不補0） |
| `open` | 開盤價 |
| `high` | 最高價 |
| `low` | 最低價 |
| `close` | 收盤價 |
| `volume` | 成交量 |
| `foreign_net` | 外資買賣超（張） |
| `prop_net` | 投信買賣超（張） |
| `dealer_net` | 自營商買賣超（張） |
| `total_net` | 三大法人總計買賣超（張） |

**注意：** T86 資料只對上市股票有效（上櫃為 0）。

---

## 買點資料格式

### 1. signal_t86_* (舊格式)
- 來源：法人買賣超 T86 資料
- 欄位：code, price, signals, count, RSI, Williams, total_net, recommendation
- 判斷邏輯：RSI < 30、Williams < -50、MACD > signal、MA200 上、法人買賣超

### 2. summary_* (新格式)
- 來源：趨勢確認
- 欄位：rank, code, name, date, signals, signal_count, RSI, Williams, recommendation
- 判斷邏輯：RSI 從 <30 回升、Williams 從 <-80 回升、MACD 金叉且 > 0、法人買賣超

---

## 自動排程

### Crontab（系統 Cron）

| 時間 | 腳本 | 用途 |
|------|------|------|
| 平日 20:00 | `daily_update.py` | 更新股價 + T86 |
| 平日 21:00 | `signal_with_t86.py` | 法人訊號分析 |
| 平日 21:10 | `signal_summary.py` | 買點訊號摘要 |

### Hermes Cron Jobs

| 時間 | 動作 |
|------|------|
| 平日 21:00 | 啟動 Streamlit Dashboard |
| 每日 02:00 | 關閉 Streamlit Dashboard |
| 每日 03:00 | 備份 Hermes 設定檔 |

---

## GitHub

- **Repo：** `https://github.com/jues5466-oss/dashboard-stock`
- **main 分支：** v2.3 最新架構
- **v2.2 分支：** v2.2 備份
