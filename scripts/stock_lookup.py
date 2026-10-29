#!/usr/bin/env python3
"""
股票代號名稱查詢工具
用法:
  python stock_lookup.py <code>          # 查詢單一股票
  python stock_lookup.py --verify <code> # 驗證並更新 stock_master.csv
  python stock_lookup.py --list          # 列出所有已記錄股票
"""

import csv
import sys
import re

MASTER_FILE = '/Volumes/AI_Drive/StockData_v2/data/money100/stock_master.csv'


def load_master():
    """載入 stock_master.csv"""
    stocks = {}
    try:
        with open(MASTER_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stocks[row['code']] = row
    except FileNotFoundError:
        pass
    return stocks


def save_master(stocks):
    """儲存 stock_master.csv"""
    with open(MASTER_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['code', 'name', 'verified', 'source', 'verified_date', 'notes'])
        writer.writeheader()
        for code, row in sorted(stocks.items()):
            writer.writerow(row)


def verify_via_yahoo(code):
    """用 tw.stock.yahoo.com 驗證股票名稱"""
    import urllib.request
    
    url = f'https://tw.stock.yahoo.com/quote/{code}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        
        # 從 HTML title 抓 name: "茂達(6138.TWO) 走勢圖 - Yahoo股市"
        match = re.search(r'^(.+?)\(' + code + r'\.(?:TW|TWO)\)', html)
        if match:
            return match.group(1).strip()
        
        # 從 <h1> 抓
        match = re.search(r'<h1[^>]*>(.+?)</h1>', html)
        if match:
            return match.group(1).strip()
        
        return None
    except Exception as e:
        print(f"  [錯誤] 無法查詢: {e}", file=sys.stderr)
        return None


def list_all(stocks):
    """列出所有股票"""
    print(f"{'代號':<6} {'名稱':<10} {'驗證':<6} {'來源':<8} {'日期':<8} 備註")
    print("-" * 60)
    for code, row in sorted(stocks.items()):
        print(f"{code:<6} {row['name']:<10} {row['verified']:<6} {row['source']:<8} {row['verified_date']:<8} {row.get('notes', '')}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == '--list':
        stocks = load_master()
        list_all(stocks)
        print(f"\n共 {len(stocks)} 檔股票")

    elif cmd == '--verify':
        if len(sys.argv) < 3:
            print("用法: stock_lookup.py --verify <code>")
            sys.exit(1)
        code = sys.argv[2]
        stocks = load_master()
        
        name = verify_via_yahoo(code)
        if name:
            old = stocks.get(code, {})
            stocks[code] = {
                'code': code,
                'name': name,
                'verified': 'true',
                'source': 'yahoo',
                'verified_date': '20260512',
                'notes': old.get('notes', '')
            }
            save_master(stocks)
            print(f"✅ {code} = {name} (已更新)")
        else:
            print(f"❌ 無法驗證 {code}")

    elif cmd == '--add':
        if len(sys.argv) < 4:
            print("用法: stock_lookup.py --add <code> <name>")
            sys.exit(1)
        code, name = sys.argv[2], sys.argv[3]
        stocks = load_master()
        stocks[code] = {
            'code': code,
            'name': name,
            'verified': 'false',
            'source': 'manual',
            'verified_date': '',
            'notes': ''
        }
        save_master(stocks)
        print(f"✅ 已新增 {code} = {name}")

    elif cmd == '--lookup':
        if len(sys.argv) < 3:
            print("用法: stock_lookup.py --lookup <code>")
            sys.exit(1)
        code = sys.argv[2]
        stocks = load_master()
        if code in stocks:
            print(f"{code} = {stocks[code]['name']}")
        else:
            print(f"❌ {code} 不在資料庫中")

    else:
        # 預設當作代號查詢
        code = cmd
        stocks = load_master()
        if code in stocks:
            print(f"{stocks[code]['name']}")
        else:
            print(f"❌ {code} 不在資料庫中")


if __name__ == '__main__':
    main()