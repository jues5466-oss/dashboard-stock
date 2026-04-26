# Stock Dashboard v2

即時股票技術分析 Dashboard，支援台灣股市。

## 主要功能

- **K線圖**: 支援蠟燭圖、成交量、技術指標疊加
- **技術指標**: KD、RSI、MACD、Williams %R、MA、CCI、OBV、MA200、ATR、DMI
- **K線型態辨識**: 锤子线、吞没形态、早晨之星、黃昏之星、十字線
- **法人進出**: 三大法人買賣超
- **買點聚合**: 多指標同時滿足時標記為聚合訊號

## 安裝需求

```bash
pip install streamlit plotly pandas
```

## 執行

```bash
python -m streamlit run scripts/dashboard_live.py --server.port 8503
```

## 目錄結構

```
StockData_v2/
├── scripts/
│   ├── dashboard_live.py    # 主程式
│   ├── daily_update.py      # 每日更新
│   ├── signal_summary.py    # 訊號摘要
│   └── ...
├── data/
│   ├── daily_data/          # 日線資料 (由 gitignore 排除)
│   └── signals/             # 訊號資料
└── RELEASE_NOTES.md
```

## 資料說明

`data/` 目錄不納入版本控制，請自行維護或使用 `scripts/download_my_stocks_history.py` 下載。
