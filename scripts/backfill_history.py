#!/usr/bin/env python3
"""
一次性回填腳本：補齊 368 檔股票 2020~2026 的歷史日檔
"""
import os
import glob
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
import urllib3
import time as time_module
urllib3.disable_warnings()

BASE_DIR = '/Volumes/AI_Drive/StockData_v2'
DAILY_DIR = f'{BASE_DIR}/data/daily_data'
MONTHLY_DIR = f'{BASE_DIR}/data/monthly_data'
YEAR_DIR = f'{BASE_DIR}/data/year_data'
ACTIVE_FILE = f'{BASE_DIR}/data/active_stocks.csv'

START_DATE = '2020-01-01'
BATCH_SIZE = 30  # 每批數量
TICKER_SUFFIX = '.TW'

print(f"[{datetime.now()}] === 回填開始 ===")

# 讀股票清單
active = pd.read_csv(ACTIVE_FILE, dtype={'code': str})
active['code'] = active['code'].astype(str).str.strip()
codes = active['code'].tolist()
print(f"股票數量：{len(codes)}")
print(f"下載區間：{START_DATE} ~ {datetime.now().strftime('%Y-%m-%d')}")

all_data = {}  # date_str -> list of rows

for i in range(0, len(codes), BATCH_SIZE):
    batch = codes[i:i+BATCH_SIZE]
    batch_num = i // BATCH_SIZE + 1
    total_batches = (len(codes) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\n批次 {batch_num}/{total_batches}：{batch[0]} ~ {batch[-1]}")

    tickers = [f"{c}{TICKER_SUFFIX}" for c in batch]
    failed = 0

    try:
        # 單一 ticker 迴圈下載（更穩定）
        for j, code in enumerate(batch):
            ticker_id = f"{code}{TICKER_SUFFIX}"
            try:
                t = yf.Ticker(ticker_id)
                hist = t.history(
                    start=START_DATE,
                    end=datetime.now().strftime('%Y-%m-%d'),
                    auto_adjust=True
                )
                if hist.empty:
                    failed += 1
                    continue

                for idx, row in hist.iterrows():
                    date_str = idx.strftime('%Y%m%d')
                    if pd.isna(row['Close']) or row['Close'] == 0:
                        continue
                    if date_str not in all_data:
                        all_data[date_str] = []
                    all_data[date_str].append({
                        'date': date_str,
                        'code': code,
                        'open': round(float(row['Open']), 2),
                        'high': round(float(row['High']), 2),
                        'low': round(float(row['Low']), 2),
                        'close': round(float(row['Close']), 2),
                        'volume': int(row['Volume'])
                    })
            except Exception as e:
                failed += 1
                continue

            if (j + 1) % 10 == 0:
                print(f"  {batch_num}.{j+1}: 已處理 {j+1}/{len(batch)} 檔...")
    except Exception as e:
        print(f"  批次 {batch_num} 失敗：{e}")

    print(f"  失敗/成功：{failed}/{len(batch)-failed}")
    time_module.sleep(1)

print(f"\n下載完成，共 {len(all_data)} 個交易日有資料")

# 寫入每日一檔
print("\n寫入 daily_data...")
written = 0
skipped = 0

for date_str in sorted(all_data.keys()):
    year = date_str[:4]
    daily_file = f"{DAILY_DIR}/{year}/{date_str}.csv"
    os.makedirs(f"{DAILY_DIR}/{year}", exist_ok=True)

    new_df = pd.DataFrame(all_data[date_str])
    new_df['code'] = new_df['code'].astype(str).str.strip()
    new_df = new_df.sort_values(['date', 'code'])

    if os.path.exists(daily_file):
        old_df = pd.read_csv(daily_file, low_memory=False)
        old_df['code'] = old_df['code'].astype(str).str.strip()
        old_codes = set(old_df['code'].unique())
        new_codes = set(new_df['code'].unique())
        add_codes = new_codes - old_codes
        if add_codes:
            new_df = new_df[new_df['code'].isin(add_codes)]
            combined = pd.concat([old_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=['date', 'code'], keep='last')
            combined = combined.sort_values(['date', 'code'])
            combined.to_csv(daily_file, index=False)
            written += 1
        else:
            skipped += 1
    else:
        new_df.to_csv(daily_file, index=False)
        written += 1

print(f"寫入完成：{written} 個日檔更新，{skipped} 個略過")

# 重建 monthly
print("\n重建 monthly_data...")
monthly_rows = {}
daily_files = sorted(glob.glob(f"{DAILY_DIR}/**/*.csv", recursive=True))
for f in daily_files:
    df = pd.read_csv(f, low_memory=False)
    ym = str(int(df['date'].iloc[0]))[:6]
    if ym not in monthly_rows:
        monthly_rows[ym] = []
    monthly_rows[ym].append(df)

for ym in sorted(monthly_rows.keys()):
    rows = monthly_rows[ym]
    combined = pd.concat(rows, ignore_index=True)
    combined['date'] = combined['date'].astype(int)
    combined = combined.drop_duplicates(subset=['date', 'code'], keep='last')
    combined = combined.sort_values(['date', 'code'])
    combined.to_csv(f"{MONTHLY_DIR}/{ym[:4]}_{ym[4:]}.csv", index=False)

print(f"  {len(monthly_rows)} 個月檔完成")

# 重建 year
print("\n重建 year_data...")
year_rows = {}
for ym, rows in sorted(monthly_rows.items()):
    year = ym[:4]
    if year not in year_rows:
        year_rows[year] = []
    year_rows[year].extend(rows)

for year in sorted(year_rows.keys()):
    combined = pd.concat(year_rows[year], ignore_index=True)
    combined['date'] = combined['date'].astype(int)
    combined = combined.drop_duplicates(subset=['date', 'code'], keep='last')
    combined = combined.sort_values(['date', 'code'])
    combined.to_csv(f"{YEAR_DIR}/{year}.csv", index=False)

print(f"  {len(year_rows)} 個年檔完成")
print(f"\n[{datetime.now()}] === 回填完成 ===")
