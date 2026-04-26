#!/usr/bin/env python3
"""
signal_with_t86.py - 法人買賣超 + 技術指標版
產出: data/signals/signal_t86_YYYYMMDD.csv

讀取架構：
  data/daily_data/YYYY/MMDD.csv    ← 每日一檔（含 OHLC + T86）
  全由 daily_data 讀取，不再需要 monthly_data 或獨立 t86/
"""
import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime

STOCK_DATA_DIR = "/Volumes/AI_Drive/StockData_v2/data"
DAILY_DIR = f"{STOCK_DATA_DIR}/daily_data"
SIGNALS_DIR = f"{STOCK_DATA_DIR}/signals"

def calc_indicators(df):
    """計算技術指標"""
    df = df.copy()

    df['MA5'] = df['close'].rolling(5).mean()
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
    df['MACD_signal'] = df['MACD'].ewm(span=9).mean()

    tp = (df['high'] + df['low'] + df['close']) / 3
    sma = tp.rolling(14).mean()
    mad = tp.rolling(14).apply(lambda x: np.abs(x - x.mean()).mean())
    df['CCI'] = (tp - sma) / (0.015 * mad)
    df['CCI'] = df['CCI'].fillna(0)

    return df

def find_latest_date():
    """找出最新的日檔日期"""
    daily_files = sorted(glob.glob(f"{DAILY_DIR}/????/????????.csv"))
    if daily_files:
        latest = os.path.basename(daily_files[-1]).replace('.csv', '')
        return latest
    return None

def load_ohlc_for_period(target_date_str):
    """從 daily_data 讀取目標月份 + 前幾個月的歷史，湊滿 200+ 交易日"""
    year = int(target_date_str[:4])
    month = int(target_date_str[4:6])

    dfs = []
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

def main():
    print("=== 信號分析（技術指標 + 法人買賣超） ===\n")

    date_str = find_latest_date()
    if date_str is None:
        print("找不到任何 OHLC 資料")
        return

    print(f"讀取 OHLC 資料，目標日期：{date_str}")
    ohlc_df = load_ohlc_for_period(date_str)
    if ohlc_df.empty:
        print("無 OHLC 資料")
        return

    latest_date = int(date_str)
    print(f"最新日期: {latest_date}")
    print(f"總記錄: {len(ohlc_df)}")

    # 計算技術指標
    print("\n計算技術指標...")
    codes = ohlc_df['code'].unique()
    print(f"股票數: {len(codes)}")

    all_indicators = []
    for code in codes:
        stock_df = ohlc_df[ohlc_df['code'] == code].sort_values('date')
        if len(stock_df) > 30:
            stock_df = calc_indicators(stock_df)
            latest = stock_df[stock_df['date'] == latest_date]
            if len(latest) > 0:
                all_indicators.append(latest)

    if all_indicators:
        indicators_df = pd.concat(all_indicators, ignore_index=True)
        print(f"有指標的股票: {len(indicators_df)}")
    else:
        print("無指標資料")
        return

    # T86 已在日檔中，直接從 indicators_df 取
    print("\n使用日檔中的 T86 資料...")

    # 生成信號
    signals = []
    for _, row in indicators_df.iterrows():
        code = row['code']
        price = row['close']
        signal_list = []

        rsi = row.get('RSI', 50)
        williams = row.get('Williams', -50)
        macd = row.get('MACD', 0)
        macd_signal = row.get('MACD_signal', 0)
        ma200 = row.get('MA200', 0)
        cci = row.get('CCI', 0)
        total_net = float(row.get('total_net', 0)) if pd.notna(row.get('total_net')) else 0
        foreign_net = float(row.get('foreign_net', 0)) if pd.notna(row.get('foreign_net')) else 0

        # 技術指標信號
        if rsi < 30:
            signal_list.append('RSI')
        elif rsi > 70:
            signal_list.append('RSI_OB')

        if williams < -80:
            signal_list.append('Williams')
        if macd > macd_signal:
            signal_list.append('MACD')
        if price > ma200 and ma200 > 0:
            signal_list.append('MA200')
        if cci < -100:
            signal_list.append('CCI')

        # 法人信號
        if total_net > 50000000:
            signal_list.append('T86_buy')
        elif total_net < -50000000:
            signal_list.append('T86_sell')
        if foreign_net > 30000000:
            signal_list.append('Foreign_buy')

        if signal_list:
            signals.append({
                'code': code,
                'price': round(price, 2),
                'signals': ','.join(signal_list),
                'signal_count': len(signal_list),
                'RSI': round(rsi, 1) if pd.notna(rsi) else 50,
                'Williams': round(williams, 1) if pd.notna(williams) else -50,
                'total_net': int(total_net),
                'foreign_net': int(foreign_net)
            })

    signals_df = pd.DataFrame(signals)
    print(f"信號數量: {len(signals_df)}")

    # 推薦
    def recommend(row):
        s = row['signals']
        sc = row['signal_count']
        has_t86 = 'T86_buy' in s or 'Foreign_buy' in s
        has_tech = 'RSI' in s or 'Williams' in s or 'MACD' in s

        if has_t86 and has_tech and sc >= 3:
            return 'strong_buy'
        elif has_t86 and sc >= 2:
            return 'buy'
        elif sc >= 3:
            return 'buy'
        elif sc >= 2:
            return 'hold'
        else:
            return 'skip'

    signals_df['recommendation'] = signals_df.apply(recommend, axis=1)
    result = signals_df.sort_values('signal_count', ascending=False)

    # 輸出
    print("\n=== Top 15 ===")
    print(result.head(15)[['code', 'price', 'signals', 'signal_count', 'recommendation']].to_string(index=False))

    print("\n=== 統計 ===")
    print(result['recommendation'].value_counts())

    # 儲存
    out_file = f"{SIGNALS_DIR}/signal_t86_{latest_date}.csv"
    result.to_csv(out_file, index=False)
    print(f"\n已儲存: {out_file}")

if __name__ == "__main__":
    main()
