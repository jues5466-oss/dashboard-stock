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

def download_stock(code, name):
    """Try .TW first, fall back to .TWO if delisted/missing."""
    for suffix in ['.TW', '.TWO']:
        ticker = f"{code}{suffix}"
        try:
            df = yf.download(ticker, period="5y", progress=False, timeout=30)
            if df is not None and len(df) > 0:
                return ticker, df
        except Exception as e:
            print(f"  {ticker} 下載失敗: {e}")
    return None, None

# Read my stocks
my_df = pd.read_csv(MY_STOCKS_FILE, dtype={"code": str})
my_df["code"] = my_df["code"].astype(str)

print(f"庫存共有 {len(my_df)} 檔")
print("開始下載歷史資料...\n")

# Download each stock and collect all rows
all_rows = []
total_records = 0

for _, row in my_df.iterrows():
    code = row['code']
    name = row['name']

    print(f"下載 {code} {name}...", end=" ")
    ticker_used, df = download_stock(code, name)

    if df is not None and len(df) > 0:
        df = df.reset_index()
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        df['code'] = code
        df = df[['Date', 'code', 'Open', 'High', 'Low', 'Close', 'Volume']]
        df.columns = ['date', 'code', 'open', 'high', 'low', 'close', 'volume']
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y%m%d').astype(int)

        all_rows.append(df)
        print(f"OK ({len(df)} 天)")
        total_records += len(df)
    else:
        print("無資料（.TW/.TWO 都失敗）")

print(f"\n下載完成，共 {total_records} 筆記錄")
print("開始寫入每日一檔...\n")

# Batch write by date - group all stocks by date and write once per date
if all_rows:
    combined = pd.concat(all_rows, ignore_index=True)
    # Group by date
    for date_str, group in combined.groupby('date'):
        year = str(date_str)[:4]
        day_file = f"{DAILY_DIR}/{year}/{date_str}.csv"
        os.makedirs(f"{DAILY_DIR}/{year}", exist_ok=True)

        # Read existing or create new
        if os.path.exists(day_file):
            existing = pd.read_csv(day_file, low_memory=False, dtype={'code': str})
            existing['code'] = existing['code'].astype(str).str.strip()
            # Remove existing rows for codes in this group
            existing = existing[~existing['code'].isin(group['code'].unique())]
            combined_group = pd.concat([existing, group], ignore_index=True)
        else:
            combined_group = group.copy()

        combined_group = combined_group.sort_values(['date', 'code'])
        combined_group.to_csv(day_file, index=False)
        print(f"  寫入 {day_file}: {len(group)} 檔")

print(f"\n總共寫入 {total_records} 筆記錄至 {DAILY_DIR}")