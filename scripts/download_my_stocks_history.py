#!/usr/bin/env python3
"""
下載我的庫存歷史資料（一次性回補用）
輸出至：data/daily_data/YYYY/MMDD.csv（每日一檔）
"""
import os
import glob
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

STOCK_DATA_DIR = '/Volumes/AI_Drive/StockData_v2'
MY_STOCKS_FILE = f'{STOCK_DATA_DIR}/data/my_stocks.csv'
DAILY_DIR = f'{STOCK_DATA_DIR}/data/daily_data'

# Read my stocks
my_df = pd.read_csv(MY_STOCKS_FILE, dtype={"code": str})
my_df["code"] = my_df["code"].astype(str)

print(f"庫存共有 {len(my_df)} 檔")
print("開始下載歷史資料...\n")

# Download each stock
total_records = 0
for _, row in my_df.iterrows():
    code = row['code']
    name = row['name']

    def download_stock(code, name):
        """Try .TW first, fall back to .TWO if delisted/missing."""
        for suffix in ['.TW', '.TWO']:
            ticker = f"{code}{suffix}"
            try:
                df = yf.download(ticker, period="5y", progress=False)
                if len(df) > 0:
                    return ticker, df
            except Exception:
                pass
        return None, None

    try:
        print(f"下載 {code} {name}...", end=" ")
        ticker_used, df = download_stock(code, name)

        if df is not None and len(df) > 0:
            df = df.reset_index()
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
            df['code'] = code
            df = df[['Date', 'code', 'Open', 'High', 'Low', 'Close', 'Volume']]
            df.columns = ['date', 'code', 'open', 'high', 'low', 'close', 'volume']
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y%m%d').astype(int)

            # 寫入每日一檔
            for _, r in df.iterrows():
                date_str = str(r['date'])
                year = date_str[:4]
                day_file = f"{DAILY_DIR}/{year}/{date_str}.csv"

                os.makedirs(f"{DAILY_DIR}/{year}", exist_ok=True)

                # 讀取現有或新建
                if os.path.exists(day_file):
                    existing = pd.read_csv(day_file, low_memory=False)
                    existing['code'] = existing['code'].astype(str).str.strip()
                    # 只針對這支股票更新或新增
                    existing = existing[existing['code'] != code]
                    new_row = pd.DataFrame([r])
                    combined = pd.concat([existing, new_row], ignore_index=True)
                else:
                    combined = pd.DataFrame([r])

                combined = combined.sort_values(['date', 'code'])
                combined.to_csv(day_file, index=False)

            print(f"OK ({len(df)} 天)")
            total_records += len(df)
        else:
            print("無資料（.TW/.TWO 都失敗）")
    except Exception as e:
        print(f"錯誤: {e}")

print(f"\n總共寫入 {total_records} 筆記錄至 {DAILY_DIR}")
