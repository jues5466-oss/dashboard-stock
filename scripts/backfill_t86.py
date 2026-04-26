#!/usr/bin/env python3
"""
將 StockData/t86/ 的完整 T86（1548檔）合併進 daily_data/YYYY/MMDD.csv
使用向量化 merge 加速
"""
import os
import glob
import pandas as pd
import time

DAILY_DIR = '/Volumes/AI_Drive/StockData_v2/data/daily_data'
T86_DIR = '/Volumes/AI_Drive/StockData_v2/data/t86'

t86_files = sorted(glob.glob(f'{T86_DIR}/t86_*.csv'))
print(f'T86 檔案數: {len(t86_files)}')
t0 = time.time()

done = 0
skipped = 0

for t86_file in t86_files:
    # date_str = YYYYMMDD
    date_str = t86_file.split('/')[-1].replace('t86_', '').replace('.csv', '')
    year = date_str[:4]
    day_file = f'{DAILY_DIR}/{year}/{date_str}.csv'

    if not os.path.exists(day_file):
        skipped += 1
        continue

    # === 向量化 merge ===
    t86_df = pd.read_csv(t86_file, dtype={'code': str}, low_memory=False)
    if 'code' not in t86_df.columns:
        print(f'  {date_str}: T86 檔無 code 欄位，跳過')
        continue
    t86_df['code'] = t86_df['code'].astype(str).str.lstrip('0').str.zfill(4)
    t86_cols = t86_df[['code', 'foreign_net', 'prop_net', 'dealer_net', 'total_net']].copy()

    df = pd.read_csv(day_file, dtype={'code': str}, low_memory=False)
    df['code'] = df['code'].astype(str).str.lstrip('0').str.zfill(4)

    # Merge：T86 覆蓋現有 NaN
    merged = df.merge(t86_cols, on='code', how='left', suffixes=('', '_t86'))
    for col in ['foreign_net', 'prop_net', 'dealer_net', 'total_net']:
        col_t86 = f'{col}_t86'
        if col_t86 in merged.columns:
            merged[col] = merged[col].combine_first(merged[col_t86])
            merged.drop(columns=[col_t86], inplace=True)

    merged.to_csv(day_file, index=False)
    done += 1
    if done % 300 == 0:
        print(f'  已處理 {done} 天 ({time.time()-t0:.0f}s)...')

elapsed = time.time() - t0
print(f'完成: {done} 天成功, {skipped} 天跳過, 耗時 {elapsed:.0f}s')

# 驗證
print('\n驗證：')
for d in ['20260424', '20260301', '20250101', '20220101', '20200102']:
    year = d[:4]
    f = f'{DAILY_DIR}/{year}/{d}.csv'
    if os.path.exists(f):
        df = pd.read_csv(f, dtype={'code': str}, low_memory=False)
        has_t86 = df['foreign_net'].notna().sum()
        row = df[df['code'].astype(str).str.lstrip('0').str.zfill(4) == '2317']
        fv = row['foreign_net'].values[0] if len(row) > 0 and pd.notna(row['foreign_net'].values[0]) else 'N/A'
        print(f'  {d}: {has_t86}/{len(df)} 檔有 T86, 2317={fv}')
