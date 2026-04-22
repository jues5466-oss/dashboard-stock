#!/usr/bin/env python3
"""每日資料更新腳本 - 法人買賣超 + 股價"""
import requests
import csv
import time
import os
import glob
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
import urllib3
urllib3.disable_warnings()

T86_DIR = '/Volumes/AI_Drive/StockData/t86'
OHLC_FILE = '/Volumes/AI_Drive/StockData/monthly_data/ohlc_full.csv'
ACTIVE_FILE = '/Volumes/AI_Drive/StockData/active_stocks.csv'
BASE_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"

print(f"[{datetime.now()}] 開始更新...")

# === T86 (法人買賣超) ===
def get_trading_dates(start, end):
    dates = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return dates

files = sorted(glob.glob(f"{T86_DIR}/t86_*.csv"))
if files:
    last_date = datetime.strptime(files[-1][-12:-4], '%Y%m%d')
else:
    last_date = datetime(2020, 1, 1)

today = datetime.now()
if today.weekday() >= 5:
    if today.weekday() == 5:
        today = today - timedelta(days=1)
    else:
        today = today - timedelta(days=2)

dates_to_fetch = get_trading_dates(last_date + timedelta(days=1), today)

if dates_to_fetch:
    print(f"抓取 T86: {len(dates_to_fetch)} 天")
    for date in dates_to_fetch:
        output = f"{T86_DIR}/t86_{date}.csv"
        try:
            r = requests.get(BASE_URL, params={'response': 'json', 'date': date, 'selectType': 'ALL'}, timeout=30, verify=False)
            data = r.json()
            if 'data' in data:
                rows = []
                for row in data['data']:
                    code = row[0].strip()
                    if code.isdigit() and 4 <= len(code) <= 6:
                        rows.append({'code': code, 'name': row[1].strip(), 'foreign_net': row[2].replace(',', ''), 
                                 'prop_net': row[3].replace(',', ''), 'dealer_net': row[4].replace(',', ''), 
                                 'total_net': row[10].replace(',', '')})
                if rows:
                    with open(output, 'w', newline='') as f:
                        w = csv.DictWriter(f, fieldnames=['code','name','foreign_net','prop_net','dealer_net','total_net'])
                        w.writeheader()
                        w.writerows(rows)
                    print(f"  {date}: {len(rows)} 檔")
        except Exception as e:
            print(f"  {date}: 錯誤 - {e}")
        time.sleep(0.3)
else:
    print("T86 已是最新")

# === OHLC (股價) ===
try:
    existing = pd.read_csv(OHLC_FILE, low_memory=False)
    existing['date'] = pd.to_datetime(existing['date'], format='mixed')
    last_date = existing['date'].max()
except:
    last_date = datetime(2020, 1, 1)

active = pd.read_csv(ACTIVE_FILE)
codes = active['code'].astype(str).tolist()

today = datetime.now()
dates = pd.date_range(start=last_date + pd.Timedelta(days=1), end=today, freq='B')

if len(dates) > 0:
    print(f"抓取 OHLC: {len(dates)} 天")
    new_data = []
    for code in codes[:50]:  # 限制一次只抓 50 檔
        try:
            ticker = yf.Ticker(f"{code}.TW")
            hist = ticker.history(start=dates[0].strftime('%Y-%m-%d'), end=today.strftime('%Y-%m-%d'))
            if not hist.empty:
                for idx, row in hist.iterrows():
                    new_data.append({'code': code, 'date': idx.strftime('%Y%m%d'), 
                                  'open': row['Open'], 'high': row['High'], 
                                  'low': row['Low'], 'close': row['Close'], 
                                  'volume': int(row['Volume'])})
        except:
            continue
    
    if new_data:
        new_df = pd.DataFrame(new_data)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined.to_csv(OHLC_FILE, index=False)
        print(f"  新增 {len(new_df)} 筆")
else:
    print("OHLC 已是最新")

print(f"[{datetime.now()}] 更新完成!")
