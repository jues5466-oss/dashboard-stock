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
import time
import sys
urllib3.disable_warnings()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trading_calendar import is_trading_day, holiday_reason

# ── 看門狗 + 單例鎖 ─────────────────────────────────────────
# 問題（2026/10/28 發現）：yfinance 偶發卡住不返回，daily_update.py 會無限
# 停滯在背景，導致當日 CSV 永遠產生不出來（資料管線靜默斷掉）。
# 對策：
#   1) flock 單例鎖：避免 crontab 與 launchd 同時啟動兩個實例互相踩檔
#   2) signal.alarm 看門狗：超過 MAX_RUNTIME 秒強制結束，避免殘留 process
#   3) flush=True：Python 對 stdout 是 block-buffer，卡住時日誌看不到進度
import fcntl
import signal

LOCK_FILE = '/tmp/stockdata_daily_update.lock'
MAX_RUNTIME = 900  # 15 分鐘；正常流程約 60-90 秒

_lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR)
try:
    fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print(f"[{datetime.now()}] 已有另一個 daily_update.py 實例在執行，跳過本次更新。")
    sys.exit(0)

def _watchdog(signum, frame):
    print(f"[{datetime.now()}] ⚠️ 超過 {MAX_RUNTIME}s 看門狗期限，強制結束（多半是 yfinance 卡住）。")
    sys.stdout.flush()
    os._exit(3)

signal.signal(signal.SIGALRM, _watchdog)
signal.alarm(MAX_RUNTIME)

# stdout 在 redirect 到檔案時是 block-buffer，卡住時日誌看不到任何進度。
# 改成 line-buffering，讓 cron/launchd 日誌即時反映進度。
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

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

# 收集每個要抓的交易日（休市日不抓，否則 yfinance 會回前一交易日資料造成假 CSV）
dates_to_fetch = []
d = last_date + timedelta(days=1)
while d <= today:
    if d.weekday() < 5 and is_trading_day(d.strftime('%Y-%m-%d')):
        dates_to_fetch.append(d)
    else:
        reason = holiday_reason(d.strftime('%Y-%m-%d')) or "週末"
        print(f"  跳過 {d.strftime('%Y%m%d')}：{reason}")
    d += timedelta(days=1)

if not dates_to_fetch:
    print("已是最新")
else:
    print(f"抓取：{len(dates_to_fetch)} 天")
    batch_size = 30

    for date in dates_to_fetch:
        date_str = date.strftime('%Y%m%d')
        year_dir = f"{DAILY_DIR}/{date.strftime('%Y')}"
        os.makedirs(year_dir, exist_ok=True)
        output_file = f"{year_dir}/{date_str}.csv"

        if os.path.exists(output_file):
            print(f"  {date_str}: 已有，略過")
            continue

        # 批次下載股價
        all_rows = []
        start_str = date.strftime('%Y-%m-%d')
        end_str = (date + timedelta(days=1)).strftime('%Y-%m-%d')

        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            tickers_tw = [f"{c}.TW" for c in batch]
            try:
                data = yf.download(
                    tickers=tickers_tw,
                    start=start_str,
                    end=end_str,
                    progress=False,
                    group_by='ticker',
                    threads=False,
                    timeout=30
                )
                for code in batch:
                    try:
                        ticker_key = f'{code}.TW'
                        use_two = False
                        if ticker_key in data.columns:
                            ticker_data = data[ticker_key]
                            if ticker_data is None or ticker_data.empty:
                                use_two = True
                            else:
                                row = ticker_data.iloc[0]
                                # 驗證列印日期確實是目標日；yfinance 在休市日會回前一交易日
                                # 的資料，若不檢查就會寫出「假交易日 CSV」。
                                if str(pd.Timestamp(row.name).strftime('%Y%m%d')) != date_str:
                                    continue
                                if pd.isna(row['Close']):
                                    use_two = True
                                else:
                                    all_rows.append({
                                        'date': date_str,
                                        'code': code,
                                        'open': round(float(row['Open']), 2),
                                        'high': round(float(row['High']), 2),
                                        'low': round(float(row['Low']), 2),
                                        'close': round(float(row['Close']), 2),
                                        'volume': int(row['Volume'])
                                    })
                        else:
                            use_two = True

                        if use_two:
                            # Fallback: 試 .TWO（上櫃/興櫃）
                            try:
                                data_two = yf.download(
                                    f'{code}.TWO',
                                    start=start_str,
                                    end=end_str,
                                    progress=False,
                                    threads=False,
                                    timeout=30
                                )
                                if data_two.empty:
                                    continue
                                # 同樣驗證日期，避免寫入前一交易日的資料
                                idx_date = str(pd.Timestamp(data_two.index[0]).strftime('%Y%m%d'))
                                if idx_date != date_str:
                                    continue
                                if isinstance(data_two.columns, pd.MultiIndex):
                                    row_dict = {}
                                    for col in data_two.columns.get_level_values(0).unique():
                                        val = data_two[(col,)].iloc[0, 0]
                                        row_dict[col.lower()] = val
                                else:
                                    row_dict = {col.lower(): data_two[col].iloc[0, 0] for col in data_two.columns}
                                if pd.isna(row_dict.get('close')):
                                    continue
                                all_rows.append({
                                    'date': date_str,
                                    'code': code,
                                    'open': round(float(row_dict.get('open', 0)), 2),
                                    'high': round(float(row_dict.get('high', 0)), 2),
                                    'low': round(float(row_dict.get('low', 0)), 2),
                                    'close': round(float(row_dict['close']), 2),
                                    'volume': int(row_dict.get('volume', 0))
                                })
                            except Exception:
                                continue
                    except Exception:
                        continue
            except Exception as e:
                print(f"  {date_str} batch {i//batch_size+1}: 下載失敗 - {e}")
            time.sleep(0.2)

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
                            'foreign_net': row[4].replace(',', ''),   # 外資+陸資 買賣超
                            'prop_net': row[10].replace(',', ''),        # 投信 買賣超
                            'dealer_net': row[11].replace(',', ''),      # 自營商 買賣超
                            'total_net': row[18].replace(',', '')
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
        time.sleep(0.3)

print(f"\n[{datetime.now()}] === 更新完成 ===")
