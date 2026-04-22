#!/usr/bin/env python3
"""
信号分析 - 整合法人买卖超 + 技术指标
"""
import pandas as pd
import numpy as np
import os

STOCK_DATA_DIR = "/Volumes/AI_Drive/StockData"
OHLC_FILE = f"{STOCK_DATA_DIR}/monthly_data/ohlc_full.csv"
T86_DIR = f"{STOCK_DATA_DIR}/t86"
SIGNALS_DIR = f"{STOCK_DATA_DIR}/signals"

def calc_indicators(df):
    """计算技术指标"""
    df = df.copy()
    
    # 移动平均
    df['MA5'] = df['close'].rolling(5).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    df['MA200'] = df['close'].rolling(200).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Williams %R
    high14 = df['high'].rolling(14).max()
    low14 = df['low'].rolling(14).min()
    df['Williams'] = -100 * (high14 - df['close']) / (high14 - low14)
    df['Williams'] = df['Williams'].fillna(-50)
    
    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
    
    # CCI
    tp = (df['high'] + df['low'] + df['close']) / 3
    sma = tp.rolling(14).mean()
    mad = tp.rolling(14).apply(lambda x: np.abs(x - x.mean()).mean())
    df['CCI'] = (tp - sma) / (0.015 * mad)
    df['CCI'] = df['CCI'].fillna(0)
    
    return df

def main():
    print("=== 信号分析（技术指标 + 法人买卖超） ===\n")
    
    # 读取 OHLC 资料
    print("读取 OHLC 资料...")
    ohlc_df = pd.read_csv(OHLC_FILE, low_memory=False)
    latest_date = ohlc_df['date'].max()
    print(f"最新日期: {latest_date}")
    print(f"总记录: {len(ohlc_df)}")
    
    # 计算技术指标
    print("\n计算技术指标...")
    codes = ohlc_df['code'].unique()
    print(f"股票数: {len(codes)}")
    
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
        print(f"有指标的股票: {len(indicators_df)}")
    else:
        print("无指标数据")
        return
    
    # 读取法人买卖超
    print("\n读取法人买卖超...")
    t86_file = f"{T86_DIR}/t86_{latest_date.replace('-','')}.csv"
    if os.path.exists(t86_file):
        t86_df = pd.read_csv(t86_file)
        print(f"法人买卖超: {len(t86_df)} 檔")
    else:
        print(f"找不到: {t86_file}")
        return
    
    # 合并
    print("\n合并资料...")
    merged = indicators_df.merge(t86_df[['code', 'foreign_net', 'prop_net', 'dealer_net', 'total_net']], on='code', how='left')
    merged['total_net'] = pd.to_numeric(merged['total_net'], errors='coerce').fillna(0)
    merged['foreign_net'] = pd.to_numeric(merged['foreign_net'], errors='coerce').fillna(0)
    
    # 生成信号
    signals = []
    for _, row in merged.iterrows():
        code = row['code']
        price = row['close']
        signal_list = []
        
        rsi = row.get('RSI', 50)
        williams = row.get('Williams', -50)
        macd = row.get('MACD', 0)
        macd_signal = row.get('MACD_signal', 0)
        ma200 = row.get('MA200', 0)
        cci = row.get('CCI', 0)
        total_net = row.get('total_net', 0)
        foreign_net = row.get('foreign_net', 0)
        
        # 技术指标信号
        if rsi < 30: signal_list.append('RSI')
        elif rsi > 70: signal_list.append('RSI_OB')
        
        if williams < -80: signal_list.append('Williams')
        if macd > macd_signal: signal_list.append('MACD')
        if price > ma200 and ma200 > 0: signal_list.append('MA200')
        if cci < -100: signal_list.append('CCI')
        
        # 法人信号
        if total_net > 50000000: signal_list.append('T86_buy')
        elif total_net < -50000000: signal_list.append('T86_sell')
        if foreign_net > 30000000: signal_list.append('Foreign_buy')
        
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
    print(f"信号数量: {len(signals_df)}")
    
    # 推荐
    def recommend(row):
        s = row['signals']
        sc = row['signal_count']
        has_t86 = 'T86_buy' in s or 'Foreign_buy' in s
        has_tech = 'RSI' in s or 'Williams' in s or 'MACD' in s
        
        if has_t86 and has_tech and sc >= 3: return 'strong_buy'
        elif has_t86 and sc >= 2: return 'buy'
        elif sc >= 3: return 'buy'
        elif sc >= 2: return 'hold'
        else: return 'skip'
    
    signals_df['recommendation'] = signals_df.apply(recommend, axis=1)
    result = signals_df.sort_values('signal_count', ascending=False)
    
    # 输出
    print("\n=== Top 15 ===")
    print(result.head(15)[['code', 'price', 'signals', 'signal_count', 'recommendation']].to_string(index=False))
    
    print("\n=== 统计 ===")
    print(result['recommendation'].value_counts())
    
    # 储存
    out_file = f"{SIGNALS_DIR}/signal_t86_{latest_date.replace('-','')}.csv"
    result.to_csv(out_file, index=False)
    print(f"\n已储存: {out_file}")

if __name__ == "__main__":
    main()
