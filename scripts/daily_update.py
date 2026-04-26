#!/usr/bin/env python3
"""
每日資料更新腳本 v2 - 法人買賣超 + 股價
輸出架構：
  data/daily_data/YYYY/MMDD.csv   ← 每日一檔（所有股票，含 T86）
  純日檔，訊號腳本讀取daily_data湊歷史
"""
import requests
import os
import glob
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
import urllib3
urllib3.disable_warnings()

# === 路徑設定 ===
BASE_DIR = '/Volumes/AI_Drive/StockData_v2'
T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
DAILY_DIR = f'{BASE_DIR}/data/daily_data'
ACTIVE_FILE = f'{BASE_DIR}/data/active_stocks.csv'

print(f"[{datetime.now()}] === 每日更新開始 ===")

# ================================================================
# 1. 股價 + T86（每日一檔）
# ================================================================
print("\n--- 股價 + T86 更新 ---")

active = pd.read_csv(ACTIVE_FILE, dtype={'code': str})
active['code'] = active['code'].astype(str).str.strip()
codes = active['code'].tolist()
print(f"股票數量：{len(codes)}")

# 找出上次最新日期
daily_files = sorted(glob.glob(f"{DAILY_DIR}/**/*.csv", recursive=True))
if daily_files:
    last_date_str = os.path.basename(daily_files[-1]).replace('.csv', '')
    last_date = datetime.strptime(last_date_str, '%Y%m%d')
else:
    last_date = datetime(2020, 1, 1)

today = datetime.now()
if today.weekday() >= 5:
    today = today - timedelta(days=1 if today.weekday() == 5 else 2)

# 收集每個要抓的交易日
dates_to_fetch = []
d = last_date + timedelta(days=1)
while d <= today:
    if d.weekday() < 5:
        dates_to_fetch.append(d)
    d += timedelta(days=1)

if not dates_to_fetch:
    print("已是最新")
else:
    print(f"抓取：{len(dates_to_fetch)} 天")
    batch_size = 50

    for date in dates_to_fetch:
        date_str = date.strftime('%Y%m%d')
        year_dir = f"{DAILY_DIR}/{date.strftime('%Y')}"
        os.makedirs(year_dir, exist_ok=True)
        output_file = f"{year_dir}/{date_str}.csv"

        if os.path.exists(output_file):
            print(f"  {date_str}: 已有，略過")
            continue

        # 批次下載股價（一次 50 檔）
        all_rows = []
        start_str = date.strftime('%Y-%m-%d')
        end_str = (date + timedelta(days=1)).strftime('%Y-%m-%d')

        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            tickers = [f"{c}.TW" for c in batch]
            try:
                data = yf.download(
                    tickers=tickers,
                    start=start_str,
                    end=end_str,
                    progress=False,
                    group_by='ticker',
                    threads=True
                )
                for code in batch:
                    try:
                        ticker_data = data[code] if code in data.columns else data.xs(code, level=1, axis=1)
                        if ticker_data is None or ticker_data.empty:
                            continue
                        row = ticker_data.iloc[0]
                        if pd.isna(row['Close']):
                            continue
                        all_rows.append({
                            'date': date_str,
                            'code': code,
                            'open': round(float(row['Open']), 2),
                            'high': round(float(row['High']), 2),
                            'low': round(float(row['Low']), 2),
                            'close': round(float(row['Close']), 2),
                            'volume': int(row['Volume'])
                        })
                    except:
                        continue
            except Exception as e:
                print(f"  {date_str} batch {i//batch_size+1}: 下載失敗 - {e}")
            # 避免 Yahoo 限速
            import time as time_module
            time_module.sleep(0.2)

        if all_rows:
            df = pd.DataFrame(all_rows)
            df = df.sort_values(['date', 'code'])
        else:
            df = pd.DataFrame(columns=['date','code','open','high','low','close','volume'])

        # 即時下載 T86 並 merge
        try:
            r = requests.get(
                T86_URL,
                params={'response': 'json', 'date': date_str, 'selectType': 'ALL'},
                timeout=30, verify=False
            )
            t86_data = r.json()
            if 'data' in t86_data:
                t86_rows = []
                for row in t86_data['data']:
                    code = row[0].strip()
                    if code.isdigit() and 4 <= len(code) <= 6:
                        t86_rows.append({
                            'code': code,
                            'foreign_net': row[2].replace(',', ''),
                            'prop_net': row[3].replace(',', ''),
                            'dealer_net': row[4].replace(',', ''),
                            'total_net': row[10].replace(',', '')
                        })
                if t86_rows:
                    t86 = pd.DataFrame(t86_rows)
                    t86['code'] = t86['code'].astype(str).str.strip()
                    df['code'] = df['code'].astype(str).str.strip()
                    df = df.merge(t86, on='code', how='left')
                    print(f"  {date_str}: {len(df)} 筆記錄（含 T86）")
                else:
                    print(f"  {date_str}: {len(df)} 筆記錄（T86 無資料）")
            else:
                print(f"  {date_str}: {len(df)} 筆記錄（T86 回傳錯誤）")
        except Exception as e:
            print(f"  {date_str}: {len(df)} 筆記錄（T86 失敗: {e}）")

        df.to_csv(output_file, index=False)
        import time as time_module
        time_module.sleep(0.3)

print(f"\n[{datetime.now()}] === 更新完成 ===")
