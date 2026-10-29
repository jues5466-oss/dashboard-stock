"""
外资買賣超追蹤報告（持股個人化版）

用法：
  python3 foreign_report.py              # 預設：今天（或前一交易日）
  python3 foreign_report.py 20260811    # 指定日期
  python3 foreign_report.py latest      # 最新一筆資料
  python3 foreign_report.py discord      # 發送到 Discord
"""

import sys
import os
import time
import json
import warnings
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trading_calendar import is_trading_day, holiday_reason
from stockdev_config import get_secret

# ── 持股設定 ────────────────────────────────────────────
STOCKS = [
    {"id": "2308", "name": "台達電"},
    {"id": "2327", "name": "國巨"},
    {"id": "2330", "name": "台積電"},
    {"id": "2454", "name": "聯發科"},
    {"id": "3017", "name": "奇鋐"},
    {"id": "3042", "name": "晶技"},
    {"id": "3443", "name": "創意"},
    {"id": "3481", "name": "群創"},
    {"id": "3665", "name": "貿聯-KY"},
    {"id": "3711", "name": "日月光投控"},
    {"id": "8358", "name": "金居"},
]

STOCK_IDS = [s["id"] for s in STOCKS]
DATA_DIR = "/Volumes/AI_Drive/StockData_v2/data/daily_data"
DISCORD_WEBHOOK = get_secret("DISCORD_WEBHOOK_FINANCE")

# ── T86 API ────────────────────────────────────────────
T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"

# T86 API 回傳單位為「股」，除以 1000 轉換為「張」
UNIT = 1000

def fetch_t86_today(date_str: str) -> pd.DataFrame:
    """當天直接 Call TWSE T86 API"""
    try:
        r = requests.get(
            T86_URL,
            params={"response": "json", "date": date_str, "selectType": "ALL"},
            timeout=30, verify=False
        )
        data = r.json()
        if "data" not in data:
            print(f"⚠️ T86 API 無資料: {data}")
            return pd.DataFrame()

        rows = []
        for row in data["data"]:
            code = str(row[0]).strip()
            if code in STOCK_IDS:
                rows.append({
                    "code": code,
                    "name": next((s["name"] for s in STOCKS if s["id"] == code), code),
                    "foreign_net": int(str(row[4]).replace(",", "").strip() or 0) // UNIT,
                    "prop_net": int(str(row[10]).replace(",", "").strip() or 0) // UNIT,
                    "dealer_net": int(str(row[11]).replace(",", "").strip() or 0) // UNIT,
                    "total_net": int(str(row[18]).replace(",", "").strip() or 0) // UNIT,
                })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = date_str
        print(f"  T86 API 取到 {len(df)} 筆記錄")
        return df
    except Exception as e:
        print(f"  ⚠️ T86 API 失敗: {e}")
        return pd.DataFrame()

def load_historical(date_str: str) -> pd.DataFrame:
    """從 CSV 讀取歷史資料（已除以 UNIT）"""
    year = date_str[:4]
    csv_path = os.path.join(DATA_DIR, year, f"{date_str}.csv")
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    df = pd.read_csv(csv_path, dtype={"code": str}, low_memory=False)
    # 如果當日 CSV 沒有法人欄位（每日更新尚未完成），往前找上一個交易日
    required_cols = {"foreign_net", "prop_net", "dealer_net", "total_net"}
    if not required_cols.issubset(df.columns):
        print(f"  ⚠️ {date_str} CSV 缺少法人欄位，往前找上一個交易日...")
        import glob
        pattern = os.path.join(DATA_DIR, year, "*.csv")
        all_files = sorted(glob.glob(pattern), reverse=True)
        for f in all_files:
            fdate = os.path.basename(f).replace(".csv", "")
            if fdate >= date_str:
                continue
            tmp = pd.read_csv(f, dtype={"code": str}, low_memory=False)
            if required_cols.issubset(tmp.columns):
                df = tmp
                print(f"  ✅ 使用 {fdate} 的 CSV 資料")
                break
        else:
            return pd.DataFrame()
    df["code"] = df["code"].astype(str).str.strip().str.lstrip("0").str.zfill(4)
    df = df[df["code"].isin(STOCK_IDS)][["date", "code", "foreign_net", "prop_net", "dealer_net", "total_net"]]
    # CSV 存的是股，轉張
    for col in ["foreign_net", "prop_net", "dealer_net", "total_net"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int) // UNIT
    print(f"  CSV 取到 {len(df)} 筆記錄")
    return df

def get_consecutive_days(code: str, target_date: str, data_dir: str, col: str = "foreign_net", lookback: int = 20) -> dict:
    """
    回測過去 lookback 天，計算同向連續天數。
    返回：{days: int, direction: 'buy'|'sell'|'none'}
    """
    year = target_date[:4]
    records = []

    for i in range(1, lookback + 2):
        d = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=i)).strftime("%Y%m%d")
        path = os.path.join(data_dir, year, f"{d}.csv")
        if os.path.exists(path):
            tmp = pd.read_csv(path, dtype={"code": str}, low_memory=False)
            tmp["code"] = tmp["code"].astype(str).str.strip().str.lstrip("0").str.zfill(4)
            row = tmp[tmp["code"] == code]
            if not row.empty:
                val = row.iloc[0]
                if col not in val.index:
                    continue
                raw = int(pd.to_numeric(val[col], errors="coerce") or 0)
                records.append({"date": d, col: raw // UNIT})

    if not records:
        return {"days": 0, "direction": "none"}

    records = sorted(records, key=lambda x: x["date"], reverse=True)
    direction = "buy" if records[0][col] > 0 else "sell" if records[0][col] < 0 else "none"
    if direction == "none":
        return {"days": 0, "direction": "none"}

    count = 1
    for i in range(1, len(records)):
        prev_sign = 1 if records[i-1][col] > 0 else -1 if records[i-1][col] < 0 else 0
        curr_sign = 1 if records[i][col] > 0 else -1 if records[i][col] < 0 else 0
        if curr_sign == prev_sign and curr_sign != 0:
            count += 1
        else:
            break

    return {"days": count, "direction": direction}

def get_latest_date() -> str:
    """取最近一個有 CSV 的交易日"""
    today = datetime.now()
    for i in range(10):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        path = os.path.join(DATA_DIR, d[:4], f"{d}.csv")
        if os.path.exists(path):
            return d
    return today.strftime("%Y%m%d")

# ── Discord 發送 ────────────────────────────────────────
def send_discord(text: str):
    import urllib.request
    import json as _json

    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    MAX_LEN = 1900
    chunks = []
    while len(text) > MAX_LEN:
        chunks.append(text[:MAX_LEN])
        text = text[MAX_LEN:]
    chunks.append(text)

    for chunk in chunks:
        payload = _json.dumps({"content": chunk}).encode()
        req = urllib.request.Request(DISCORD_WEBHOOK, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 204:
                    print(f"⚠️ Discord 響應: {resp.status}")
        except Exception as e:
            print(f"⚠️ Discord 發送失敗: {e}")
        time.sleep(0.3)
    print("✅ Discord 發送成功")

def build_report(today_df: pd.DataFrame, target_date: str) -> str:
    """產出報告文字"""
    lines = [f"🏛️ 三大法人日報 — {target_date[:4]}/{target_date[4:6]}/{target_date[6:]}"]
    lines.append(f"*（針對持股追蹤，單位：張）*\n")

    has_today_data = not today_df.empty
    stock_map = {s["id"]: s["name"] for s in STOCKS}

    if has_today_data:
        today_df = today_df.sort_values("foreign_net", key=abs, ascending=False)
        buys = today_df[today_df["foreign_net"] > 0].sort_values("foreign_net", ascending=False)
        sells = today_df[today_df["foreign_net"] < 0].sort_values("foreign_net")

        if not buys.empty:
            lines.append("📈 外資買超：")
            for _, r in buys.iterrows():
                code = r["code"]
                net = int(r["foreign_net"])
                name = stock_map.get(code, code)
                consec = get_consecutive_days(code, target_date, DATA_DIR)
                if consec["direction"] == "buy" and consec["days"] >= 2:
                    consec_str = f"（連續買超{consec['days']}天）"
                else:
                    consec_str = ""
                lines.append(f"• {name}({code})：+{net:,}張 {consec_str}")
            lines.append("")

        if not sells.empty:
            lines.append("📉 外資賣超：")
            for _, r in sells.iterrows():
                code = r["code"]
                net = int(r["foreign_net"])
                name = stock_map.get(code, code)
                consec = get_consecutive_days(code, target_date, DATA_DIR)
                if consec["direction"] == "sell" and consec["days"] >= 2:
                    consec_str = f"（連續賣超{consec['days']}天）"
                else:
                    consec_str = ""
                lines.append(f"• {name}({code})：{net:,}張 {consec_str}")
            lines.append("")

        # ── 投信、自營商合計 ───────────────────────────
        prop_total = int(today_df["prop_net"].sum())
        dealer_total = int(today_df["dealer_net"].sum())
        prop_icon = "📗" if prop_total >= 0 else "📕"
        dealer_icon = "📗" if dealer_total >= 0 else "📕"
        lines.append(f"{prop_icon} 投信合計：{'+' if prop_total >= 0 else ''}{prop_total:,}張")
        lines.append(f"{dealer_icon} 自營商合計：{'+' if dealer_total >= 0 else ''}{dealer_total:,}張")
        lines.append("")

        # ── 投信個股買賣超 ───────────────────────────
        prop_buys = today_df[today_df["prop_net"] > 0].sort_values("prop_net", ascending=False)
        prop_sells = today_df[today_df["prop_net"] < 0].sort_values("prop_net")

        if not prop_buys.empty:
            lines.append("📗 投信買超：")
            for _, r in prop_buys.iterrows():
                code = r["code"]
                net = int(r["prop_net"])
                name = stock_map.get(code, code)
                consec = get_consecutive_days(code, target_date, DATA_DIR, col="prop_net")
                if consec["direction"] == "buy" and consec["days"] >= 2:
                    consec_str = f"（連續買超{consec['days']}天）"
                else:
                    consec_str = ""
                lines.append(f"• {name}({code})：+{net:,}張 {consec_str}")
            lines.append("")

        if not prop_sells.empty:
            lines.append("📕 投信賣超：")
            for _, r in prop_sells.iterrows():
                code = r["code"]
                net = int(r["prop_net"])
                name = stock_map.get(code, code)
                consec = get_consecutive_days(code, target_date, DATA_DIR, col="prop_net")
                if consec["direction"] == "sell" and consec["days"] >= 2:
                    consec_str = f"（連續賣超{consec['days']}天）"
                else:
                    consec_str = ""
                lines.append(f"• {name}({code})：{net:,}張 {consec_str}")
            lines.append("")

        # ── 警示 ─────────────────────────────────
        alerts = []
        for _, r in today_df.iterrows():
            net = int(r["foreign_net"])
            code = r["code"]
            name = stock_map.get(code, code)
            if abs(net) > 3000:
                direction = "買超" if net > 0 else "賣超"
                alerts.append(f"⚠️ {name}({code}) 外資淨{direction} **{abs(net):,}張**")

        if alerts:
            lines.append("──────────────────────────────")
            lines.append("**⚠️ 重量級異動（>3000張）：**")
            for a in alerts:
                lines.append(a)

    else:
        lines.append(f"⏳ 今日（{target_date}）T86 資料尚未更新")

    return "\n".join(lines)

def main():
    mode = "report"
    target_date = None

    args = list(sys.argv[1:])
    # 先把 mode 旗標挑出來，剩下的當作日期參數。
    # 舊版只接受單一參數，導致 `foreign_report.py 20261028 discord` 會把
    # "discord" 忽略掉、mode 停在 report → 只印在 stdout 不發 Discord。
    for i, a in enumerate(list(args)):
        if a == "discord":
            mode = "discord"
            args.pop(i)
            break

    for arg in args:
        if arg.isdigit() and len(arg) == 8:
            target_date = arg
        elif arg == "latest":
            target_date = get_latest_date()
        else:
            print("用法: python3 foreign_report.py [YYYYMMDD|latest] [discord]")
            return

    if target_date is None:
        target_date = get_latest_date()

    # 休市日跳過（避免用前一交易日資料冒充當日）
    iso = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
    if not is_trading_day(iso):
        reason = holiday_reason(iso)
        print(f"⏭️  {target_date} 休市（{reason}），跳過外資買賣超報告，不發送 Discord。")
        return

    print(f"📊 外資買賣超報告 — {target_date}")

    # 優先用 API 當天，沒有則讀 CSV
    today_df = fetch_t86_today(target_date)
    if today_df.empty:
        print("  → 改用 CSV 歷史資料")
        today_df = load_historical(target_date)

    report = build_report(today_df, target_date)
    print(f"\n{report}")

    if mode == "discord":
        print("\n--- 發送 Discord ---")
        send_discord(report)

if __name__ == "__main__":
    main()
