#!/usr/bin/env python3
"""
下載我的庫存歷史資料
"""
import os
import glob
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

STOCK_DATA_DIR = '/Volumes/AI_Drive/StockData'
OHLC_FILE = f'{STOCK_DATA_DIR}/monthly_data/ohlc_full.csv'
MY_STOCKS_FILE = '/Volumes/AI_Drive/StockData/my_stocks.csv'

# Read my stocks
my_df = pd.read_csv(MY_STOCKS_FILE, dtype={"code": str})
my_df["code"] = my_df["code"].astype(str)

print(f"庫存共有 {len(my_df)} 檔")
print("開始下載歷史資料...\n")

# Create monthly_data folder if not exists
os.makedirs(f'{STOCK_DATA_DIR}/monthly_data', exist_ok=True)

# Read existing data if exists
if os.path.exists(OHLC_FILE):
    existing_df = pd.read_csv(OHLC_FILE, low_memory=False)
    existing_df['code'] = existing_df['code'].astype(str)
    existing_codes = set(existing_df['code'].unique())
else:
    existing_df = pd.DataFrame()
    existing_codes = set()

# Download each stock
new_data = []
for _, row in my_df.iterrows():
    code = row['code']
    name = row['name']
    
    # Try to get data
    try:
        # Add .TW for Taiwan stocks if not ETF
        if code.startswith('00'):
            ticker = f"{code}.TW"
        else:
            ticker = f"{code}.TW"
        
        print(f"下載 {code} {name}...", end=" ")
        
        df = yf.download(ticker, period="5y", progress=False)
        
        if len(df) > 0:
            df = df.reset_index()
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
            df['code'] = code
            
            # Keep only needed columns
            df = df[['Date', 'code', 'Open', 'High', 'Low', 'Close', 'Volume']]
            df.columns = ['date', 'code', 'open', 'high', 'low', 'close', 'volume']
            
            # Convert date to YYYYMMDD format
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y%m%d').astype(int)
            
            new_data.append(df)
            print(f"OK ({len(df)} 天)")
        else:
            print("無資料")
    except Exception as e:
        print(f"錯誤: {e}")

# Combine and save
if new_data:
    combined = pd.concat(new_data, ignore_index=True)
    
    if len(existing_df) > 0:
        combined = pd.concat([existing_df, combined], ignore_index=True)
        combined = combined.drop_duplicates(subset=['date', 'code'], keep='last')
    
    combined = combined.sort_values(['code', 'date'])
    combined.to_csv(OHLC_FILE, index=False)
    
    print(f"\n總共 {len(combined)} 筆記錄已儲存到 {OHLC_FILE}")
else:
    print("\n沒有新資料")
