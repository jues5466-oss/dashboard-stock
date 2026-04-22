#!/usr/bin/env python3
"""
法人买卖超资料抓取 - 完整版
抓取 2020-01-01 到现在所有股票的资料
"""
import json
import os
import subprocess
from datetime import datetime, timedelta
import pandas as pd
import time

STOCK_DATA_DIR = "/Volumes/AI_Drive/StockData"
T86_DIR = f"{STOCK_DATA_DIR}/t86"

# 所有产业别代码
INDUSTRY_MAP = {
    "01": "水泥", "02": "食品", "03": "纺织", "04": "电机",
    "05": "化工", "06": "资讯服务", "07": "电子", "08": "电子零件",
    "09": "电子通路", "10": "资服", "11": "半导体", "12": "塑化",
    "13": "钢铁", "14": "橡胶", "15": "汽车", "16": "电子",
    "17": "金融", "18": "贸易", "19": "观光", "20": "运输",
    "21": " 营造", "22": "建设", "23": "其他", "24": "生技",
    "25": "医疗", "26": "环保", "27": "油电", "28": "能量",
    "29": "车电", "30": "电子", "31": " Electronic", "32": "电商", "33": " App"
}

# 读取活跃股票
active_df = pd.read_csv(f"{STOCK_DATA_DIR}/active_stocks.csv")
ACTIVE_CODES = set(active_df['code'].astype(str).tolist())
print(f"活跃股票: {len(ACTIVE_CODES)} 檔")

def fetch_t86_by_type(select_type, date_str):
    """抓取单日的法人买卖超（所有产业）"""
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?selectType={select_type}&date={date_str}&response=json"
    try:
        cmd = f"curl -s '{url}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        
        if data.get('stat') != 'OK':
            return []
        
        records = []
        for row in data.get('data', []):
            code = row[0].strip()
            if code in ACTIVE_CODES:
                records.append({
                    'code': code,
                    'date': date_str,
                    'foreign_net': row[4].replace(',', '').strip() if len(row) > 4 else '0',
                    'prop_net': row[10].replace(',', '').strip() if len(row) > 10 else '0',
                    'dealer_net': row[14].replace(',', '').strip() if len(row) > 14 else '0',
                    'total_net': row[18].replace(',', '').strip() if len(row) > 18 else '0',
                })
        return records
    except Exception as e:
        print(f"Error {select_type}/{date_str}: {e}")
        return []

def fetch_t86_date(date_str):
    """抓取单日所有产业的法人买卖超"""
    all_data = []
    for st_type in INDUSTRY_MAP.keys():
        records = fetch_t86_by_type(st_type, date_str)
        all_data.extend(records)
        time.sleep(0.3)  # 避免太快被封
    return all_data

def generate_dates(start_date, end_date):
    """生成日期范围内的所有交易日"""
    dates = []
    current = start_date
    while current <= end_date:
        # 跳过周末
        if current.weekday() < 5:
            dates.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return dates

def main():
    print("=== 开始抓取法人买卖超 ===")
    print(f"目标股票: {len(ACTIVE_CODES)} 檔")
    
    # 设定日期范围
    start_date = datetime(2020, 1, 2)
    end_date = datetime.now()
    
    dates = generate_dates(start_date, end_date)
    print(f"总天数: {len(dates)}")
    
    # 检查已有多少
    existing = set()
    for f in os.listdir(T86_DIR):
        if f.startswith('t86_') and f.endswith('.csv'):
            existing.add(f.replace('t86_', '').replace('.csv', ''))
    
    new_dates = [d for d in dates if d not in existing]
    print(f"需要抓取: {len(new_dates)} 天")
    print(f"已有: {len(existing)} 天")
    
    # 抓取资料
    all_records = []
    for i, date_str in enumerate(new_dates[:10]):  # 先测试10天
        print(f"处理 {date_str} ({i+1}/{len(new_dates)})...", end=" ")
        records = fetch_t86_date(date_str)
        print(f" {len(records)} 檔")
        
        if records:
            all_records.extend(records)
    
    print(f"\n=== 测试结果 ===")
    print(f"抓取天数: {len(new_dates[:10])}")
    print(f"总记录: {len(all_records)}")
    
    # 统计
    if all_records:
        df = pd.DataFrame(all_records)
        print(f"\n股票数: {df['code'].nunique()}")
        print(df.head())

if __name__ == "__main__":
    main()
