#!/usr/bin/env python3
"""
signal_summary.py - 趨勢確認版
產出: data/signals/summary_YYYYMMDD.csv

讀取架構：
  data/daily_data/YYYY/MMDD.csv    ← 每日一檔（含 OHLC + T86）
  全由 daily_data 讀取，不再需要 monthly_data 或獨立 t86/
"""
import pandas as pd
import os
import glob
from datetime import datetime
import numpy as np

STOCK_DATA_DIR = '/Volumes/AI_Drive/StockData_v2/data'
SIGNALS_DIR = f'{STOCK_DATA_DIR}/signals'
DAILY_DIR = f'{STOCK_DATA_DIR}/daily_data'

SIGNAL_CONDITIONS = {
    'KD': lambda row, prev: (prev['K'] < prev['D']) & (row['K'] > row['D']) & (row['K'] < 30),
    'RSI': lambda row, prev: (prev['RSI'] < 30) & (row['RSI'] >= 30),
    'MACD': lambda row, prev: (prev['MACD'] < prev['MACD_sig']) & (row['MACD'] > row['MACD_sig']) & (row['MACD'] > 0),
    'Williams': lambda row, prev: (prev['Williams'] < -80) & (row['Williams'] >= -80),
    'MA': lambda row, prev: (prev['MA20'] < prev['MA60']) & (row['MA20'] > row['MA60']),
    'CCI': lambda row, prev: (prev['CCI'] < -80) & (row['CCI'] >= -80),
    'MA200': lambda row, prev: (prev['close'] <= prev['MA200']) & (row['close'] > row['MA200']),
}

def calc_indicators(df):
    df = df.copy()
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    df['MA200'] = df['close'].rolling(200).mean()

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    high14 = df['high'].rolling(14).max()
    low14 = df['low'].rolling(14).min()
    df['Williams'] = -100 * (high14 - df['close']) / (high14 - low14)
    df['Williams'] = df['Williams'].fillna(-50)

    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_sig'] = df['MACD'].ewm(span=9).mean()

    low_min = df['low'].rolling(9).min()
    high_max = df['high'].rolling(9).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min)
    df['K'] = k.rolling(3).mean()
    df['D'] = df['K'].rolling(3).mean()

    tp = (df['high'] + df['low'] + df['close']) / 3
    sma = tp.rolling(14).mean()
    mad = tp.rolling(14).apply(lambda x: abs(x - x.mean()).mean())
    df['CCI'] = (tp - sma) / (0.015 * mad)
    df['CCI'] = df['CCI'].fillna(0)

    return df

def find_latest_date():
    """找出最新的日檔日期"""
    daily_files = sorted(glob.glob(f"{DAILY_DIR}/????/????????.csv"))
    if daily_files:
        # 取倒數第一個（最新的）
        latest = os.path.basename(daily_files[-1]).replace('.csv', '')
        return latest
    return None

def load_ohlc_for_period(target_date_str):
    """
    從 daily_data 讀取目標月份 + 前幾個月的歷史，湊滿 200+ 交易日的資料
    """
    year = int(target_date_str[:4])
    month = int(target_date_str[4:6])

    dfs = []

    # 往前讀約 10 個月的日檔（足以湊夠 200+ 交易日）
    for offset_months in range(10):
        m = month - offset_months
        y = year
        while m <= 0:
            m += 12
            y -= 1
        month_str = f"{y}{m:02d}"
        pattern = f"{DAILY_DIR}/{y}/{month_str}??.csv"
        month_files = sorted(glob.glob(pattern))
        for f in month_files:
            try:
                df = pd.read_csv(f, low_memory=False, dtype={'code': str})
                df['code'] = df['code'].astype(str).str.strip()
                dfs.append(df)
            except:
                continue

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.drop_duplicates(subset=['date', 'code'], keep='last')
    combined['date'] = pd.to_numeric(combined['date'], errors='coerce')
    combined = combined.sort_values(['code', 'date'])
    return combined

def generate_summary(date_str=None):
    if date_str is None:
        date_str = find_latest_date()
        if date_str is None:
            print("找不到任何 OHLC 資料")
            return

    print(f"=== 買點摘要產生 ===")
    print(f"目標日期: {date_str}")

    # 讀取足夠歷史計算指標
    print("讀取 OHLC 歷史...")
    ohlc_df = load_ohlc_for_period(date_str)
    if ohlc_df.empty:
        print("無 OHLC 資料")
        return

    latest_date = int(date_str)
    print(f"最新日期: {latest_date}")
    print(f"總記錄: {len(ohlc_df)}")

    # 讀取股票名稱
    active = pd.read_csv(f'{STOCK_DATA_DIR}/active_stocks.csv', dtype={'code': str})
    active['code'] = active['code'].astype(str).str.strip()
    name_dict = active.set_index('code')['name'].to_dict()

    codes = ohlc_df['code'].unique()
    results = []

    print(f"檢查 {len(codes)} 檔股票...")
    for code in codes:
        stock = ohlc_df[ohlc_df['code'] == code].sort_values('date').reset_index(drop=True)
        if len(stock) > 60:
            stock = calc_indicators(stock)

            if len(stock) >= 2:
                row = stock.iloc[-1]
                prev = stock.iloc[-2]

                signal_list = []
                for ind, cond in SIGNAL_CONDITIONS.items():
                    try:
                        if cond(row, prev):
                            signal_list.append(ind)
                    except:
                        pass

                if signal_list:
                    rsi = row.get('RSI', 50)
                    williams = row.get('Williams', -50)

                    # T86 已經在日檔中，直接取
                    total_net = int(row.get('total_net', 0)) if pd.notna(row.get('total_net')) else 0

                    results.append({
                        'code': code,
                        'name': name_dict.get(code, ''),
                        'price': round(row['close'], 2),
                        'signals': ','.join(signal_list),
                        'count': len(signal_list),
                        'RSI': round(rsi, 1) if pd.notna(rsi) else 50,
                        'Williams': round(williams, 1) if pd.notna(williams) else -50,
                        'total_net': total_net
                    })

    df = pd.DataFrame(results)

    if len(df) == 0:
        print('沒有找到信號')
        return

    def rec(row):
        if row['count'] >= 2:
            return 'strong_buy'
        elif row['count'] == 1:
            return 'buy'
        return 'skip'

    df['recommendation'] = df.apply(rec, axis=1)

    rec_order = {'strong_buy': 0, 'buy': 1, 'skip': 2}
    df['rec_order'] = df['recommendation'].map(rec_order)
    df = df.sort_values(['rec_order', 'count'], ascending=[True, False])
    df = df.reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'rank'

    print(f'\n=== 買點摘要 ({latest_date}) ===')
    s = len(df[df['recommendation'] == 'strong_buy'])
    b = len(df[df['recommendation'] == 'buy'])
    sk = len(df[df['recommendation'] == 'skip'])
    print(f'強買: {s}, 買: {b}, 跳過: {sk}')

    result = df[df['recommendation'].isin(['strong_buy', 'buy'])]
    print(f'\n=== 買點清單 ({len(result)}檔) ===')
    for _, r in result.head(10).iterrows():
        print(f"{int(r.name):2}. {r['code']} {r.get('name', ''):8} | {r['signals']:20} | {r['recommendation']}")

    summary_out = f'{SIGNALS_DIR}/summary_{latest_date}.csv'
    df.to_csv(summary_out, index=True, encoding='utf-8-sig')
    print(f'\n已產出: {summary_out}')

if __name__ == '__main__':
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    generate_summary(date)
