# Stock Dashboard v2 技術文件

## 系統概覽

**Stock Dashboard v2** 是一套台股分析系統，包含：
- 即時 Dashboard 視覺化（K線、均線、買點訊號、法人動向）
- 每日自動更新股價 + 法人買賣超資料（T86）
- 買點/賣點訊號分析

---

## 目錄結構

```
StockData_v2/
├── scripts/
│   ├── dashboard_live.py      # Streamlit Dashboard（主力視覺化）
│   ├── daily_update.py       # 每日資料更新（股價 + T86）
│   ├── signal_with_t86.py    # 法人買賣超訊號分析
│   ├── signal_summary.py      # 買點訊號摘要
│   ├── download_my_stocks_history.py  # 庫存股歷史回補
│   ├── backfill_history.py   # 歷史股價回補
│   └── backfill_t86.py      # T86 歷史回補
├── data/
│   ├── daily_data/           # 每日一檔（核心資料）
│   │   ├── 2020/
│   │   ├── 2021/
│   │   ├── 2022/
│   │   ├── 2023/
│   │   ├── 2024/
│   │   ├── 2025/
│   │   └── 2026/
│   │       └── 20260424.csv  # 格式：date,code,open,high,low,close,volume,foreign_net,prop_net,dealer_net,total_net
│   ├── signals/              # 訊號輸出
│   │   ├── summary_YYYYMMDD.csv    # 買點訊號
│   │   └── signal_t86_YYYYMMDD.csv # 法人訊號
│   ├── active_stocks.csv     # 370 檔追蹤股票清單
│   ├── my_stocks.csv         # 個人庫存股（子集合）
│   └── excluded_stocks.csv   # 排除清單
└── logs/
    ├── signal.log            # signal_summary.py 執行日誌
    └── signal_t86.log        # signal_with_t86.py 執行日誌
```

---

## 資料格式

### 日檔格式（`data/daily_data/YYYY/MMDD.csv`）

| 欄位 | 說明 |
|------|------|
| `date` | 日期（YYYYMMDD） |
| `code` | 股票代碼（str，4碼不補0，如 `2330`） |
| `open` | 開盤價 |
| `high` | 最高價 |
| `low` | 最低價 |
| `close` | 收盤價 |
| `volume` | 成交量 |
| `foreign_net` | 外資買賣超（張） |
| `prop_net` | 投信買賣超（張） |
| `dealer_net` | 自營商買賣超（張） |
| `total_net` | 三大法人總計買賣超（張） |

**重要：**
- 上市股票 `.TW`（如 2330.TW）
- 上櫃股票 `.TWO`（如 3324.TWO）
- T86 資料只對上市股票有效（上櫃為 0）

---

## 腳本說明

### 1. `daily_update.py` — 每日資料更新

**用途：** 每個交易日自動抓取最新股價 + 法人買賣超資料

**輸出：** `data/daily_data/YYYY/MMDD.csv`（每日一檔，涵蓋所有 370 檔股票）

**邏輯流程：**
1. 讀取 `active_stocks.csv`（370 檔）
2. 檢查 `daily_data/` 最新日期
3. 抓取間隔內所有交易日
4. 批次下載股價（yfinance，`.TW` → `.TWO` fallback）
5. 抓取 T86 法人買賣超（TWSE API）
6. 合併寫入當日 CSV

**手動執行：**
```bash
python3 /Volumes/AI_Drive/StockData_v2/scripts/daily_update.py
```

**Crontab（系統已設定）：**
```
平日 20:00  → daily_update.py      # 更新股價 + T86
```

---

### 2. `dashboard_live.py` — Dashboard 主程式

**用途：** Streamlit 即時視覺化網頁

**技術棧：** Python + Streamlit + Plotly + yfinance

**功能：**
- 股票選擇（可搜尋）
- K線圖（Plotly Candlestick）
- 技術指標：MA20、MA60、MA200、Bollinger Bands、KD、RSI、MACD、威廉指標
- 法人買賣超長條圖
- **買點策略偵測**（V4 版本多指標獨立買點）

**買點偵測指標：**
| 指標 | 說明 |
|------|------|
| MA20 | 收盤價站上20日均線 |
| MA60 | 收盤價站上60日均線 |
| Bollinger | 價格接觸布林帶下軌 |
| KD黃金交叉 | K線由下往上穿越D線 |
| RSI超賣 | RSI < 30 |
| MACD黃金交叉 | MACD由負轉正 |
| 法人買超 | 三大法人合計買超 > 一定張數 |

**啟動命令：**
```bash
cd /Volumes/AI_Drive/StockData_v2/scripts
python3 -m streamlit run dashboard_live.py --server.headless true --server.port 8503
```

**Dashboard 網址：** `http://17.0.0.56:8503`

**Crontab（Hermes 已設定）：**
```
21:00 → 啟動 Dashboard（Hermes cron job）
02:00 → 關閉 Dashboard（Hermes cron job）
```

---

### 3. `signal_with_t86.py` — 法人買賣超訊號

**用途：** 每天分析法人買賣超，產生訊號 CSV

**輸出：** `data/signals/signal_t86_YYYYMMDD.csv`

**邏輯：** 讀取 `daily_data/`，對每檔股票計算近 N 日法人累計買賣超，找出異常買超/賣超訊號

**Crontab：**
```
平日 21:00 → signal_with_t86.py
```

---

### 4. `signal_summary.py` — 買點訊號摘要

**用途：** 結合技術指標 + 法人資料，找出潛在買點

**輸出：** `data/signals/summary_YYYYMMDD.csv`

**邏輯：**
1. 讀取 `daily_data/` 近半年資料
2. 計算 MA20、MA60、KD、RSI、Bollinger Bands
3. 找出出現買點的股票
4. 輸出摘要 CSV

**Crontab：**
```
平日 21:10 → signal_summary.py
```

---

### 5. `download_my_stocks_history.py` — 庫存股歷史回補

**用途：** 一次性的歷史資料回補，針對 `my_stocks.csv`（個人庫存）

**邏輯：**
1. 讀取 `my_stocks.csv`
2. 用 yfinance 回補最早期開始的全部歷史
3. 輸出寫入 `daily_data/YYYY/MMDD.csv`

**執行（一次性）：**
```bash
python3 /Volumes/AI_Drive/StockData_v2/scripts/download_my_stocks_history.py
```

---

## 自動排程總覽

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

## 資料範圍

| 項目 | 數值 |
|------|------|
| 股票數量 | 370 檔（`active_stocks.csv`）|
| 時間範圍 | 2020-01-02 ~ 最新交易日 |
| 日檔數量 | 1529 天 |
| T86 覆蓋 | 1548 天（全部有法人資料） |

---

## GitHub

- **Repo：** `https://github.com/jues5466-oss/dashboard-stock`
- **main 分支：** v2.2 新架構（當前使用）
- **v2.2 分支：** 舊架構備份

---

## 環境需求

- Python 3.x（需 yfinance、pandas、streamlit、plotly）
- 路徑：`/Volumes/AI_Drive/StockData_v2/`
- Streamlit 需加 `--server.headless true` 參數啟動

---

## 常見問題

**Q：法人買賣超都是 0？**
A：T86 資料只對上市股票有效。上櫃股票（`.TWO`）的法人欄位會是 0。

**Q：某些股票下載不到？**
A：先用 `.TW` 嘗試，失敗後 fallback 到 `.TWO`（上櫃）。

**Q：Dashboard 看不到法人圖？**
A：檢查 `signal_with_t86.py` 是否成功執行，日檔是否有 `foreign_net` 欄位。

**Q：如何新增股票？**
A：編輯 `data/active_stocks.csv`，加入股票代碼和名稱。
