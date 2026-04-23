#!/usr/bin/env python3
"""
signal_summary.py - 趋势确认版
产出: signal_t86_YYYYMMDD.csv + summary_YYYYMMDD.csv
"""
import pandas as pd
import os
from datetime import datetime
import numpy as np

STOCK_DATA_DIR = '/Volumes/AI_Drive/StockData'
SIGNALS_DIR = f'{STOCK_DATA_DIR}/signals'
OHLC_FILE = f'{STOCK_DATA_DIR}/monthly_data/ohlc_full.csv'
T86_DIR = f'{STOCK_DATA_DIR}/t86'

SIGNAL_CONDITIONS = {
    'KD': lambda row, prev: (prev['K'] < prev['D']) & (row['K'] > row['D']) & (row['K'] < 30),
    'RSI': lambda row, prev: (prev['RSI'] < 30) & (row['RSI'] >= 30),
    'MACD': lambda row, prev: (prev['MACD'] < prev['MACD_sig']) & (row['MACD'] > row['MACD_sig']) & (row['MACD'] > 0),
    'Williams': lambda row, prev: (prev['Williams'] < -80) & (row['Williams'] >= -80),
    'MA': lambda row, prev: (prev['MA20'] < prev['MA60']) & (row['MA20'] > row['MA60']),
    'CCI': lambda row, prev: (prev['CCI'] < -80) & (row['CCI'] >= -80),
    'MA200': lambda row, prev: (prev['Close'] <= prev['MA200']) & (row['Close'] > row['MA200']),
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

def generate_summary(date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    
    print(f"读取 OHLC 资料...")
    ohlc_df = pd.read_csv(OHLC_FILE, low_memory=False)
    
    def fix_date(d):
        if isinstance(d, str):
            return d[:10].replace('-','') if '-' in d else d[:8]
        return str(d)
    
    ohlc_df['date'] = ohlc_df['date'].apply(fix_date)
    ohlc_df['date'] = pd.to_numeric(ohlc_df['date'], errors='coerce')
    ohlc_df['code'] = ohlc_df['code'].astype(str).str.strip()
    
    latest_date = int(ohlc_df['date'].max())
    print(f"日期: {latest_date}")
    
    # 读取法人买卖超
    t86_file = f"{T86_DIR}/t86_{latest_date}.csv"
    if os.path.exists(t86_file):
        t86_df = pd.read_csv(t86_file)
        t86_df['code'] = t86_df['code'].astype(str).str.strip()
    else:
        t86_df = None
    
    # 读取股票名称
    active = pd.read_csv(f'{STOCK_DATA_DIR}/active_stocks.csv')
    active['code'] = active['code'].astype(str).str.strip()
    name_dict = active.set_index('code')['name'].to_dict()
    
    codes = ohlc_df['code'].unique()
    results = []
    
    print(f"检查 {len(codes)} 檔股票...")
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
                    
                    total_net = 0
                    if t86_df is not None:
                        t86_row = t86_df[t86_df['code'] == code]
                        if len(t86_row) > 0:
                            total_net = int(t86_row['total_net'].iloc[0])
                    
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
        print('没有找到信号')
        return
    
    def rec(row):
        if row['count'] >= 2: return 'strong_buy'
        elif row['count'] == 1: return 'buy'
        return 'skip'
    
    df['recommendation'] = df.apply(rec, axis=1)
    
    # 产出 signal_t86_*.csv
    # signal_out (skip)
    # df.to_csv(signal_out, index=False)  # skip
    print(f'\n已产出: {len(signal_list)} 筆')
    
    # 产出 summary_*.csv
    rec_order = {'strong_buy': 0, 'buy': 1, 'skip': 2}
    df['rec_order'] = df['recommendation'].map(rec_order)
    df = df.sort_values(['rec_order', 'count'], ascending=[True, False])
    df = df.reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'rank'
    
    print(f'\n=== 买點摘要 ({latest_date}) ===')
    s = len(df[df['recommendation']=='strong_buy'])
    b = len(df[df['recommendation']=='buy'])
    sk = len(df[df['recommendation']=='skip'])
    print(f'强买: {s}, 买: {b}, 跳过: {sk}')
    
    result = df[df['recommendation'].isin(['strong_buy', 'buy'])]
    print(f'\n=== 买點清单 ({len(result)}檔) ===')
    for _, r in result.head(10).iterrows():
        print(f"{r.name:2}. {r['code']} {r.get('name',''):8} | {r['signals']:20} | {r['recommendation']}")
    
    summary_out = f'{SIGNALS_DIR}/summary_{latest_date}.csv'
    df.to_csv(summary_out, index=True, encoding='utf-8-sig')
    print(f'\n已产出: {summary_out}')

if __name__ == '__main__':
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    generate_summary(date)
