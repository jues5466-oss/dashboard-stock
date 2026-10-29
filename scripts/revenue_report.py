#!/usr/bin/env python3
"""
月營收報告 — 持股月營收追蹤
資料來源：FinMind API (https://api.finmindtrade.com)
"""

import requests
import json
import time
import os
import sys
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stockdev_config import get_secret

# ── Config ──────────────────────────────────────────────
DISCORD_WEBHOOK = get_secret("DISCORD_WEBHOOK_REVENUE")

# 持股（用戶每月更新一次）
STOCKS = [
    {"id": "2330", "name": "台積電"},
    {"id": "2454", "name": "聯發科"},
    {"id": "3443", "name": "創意"},
    {"id": "3017", "name": "奇鋐"},
    {"id": "3481", "name": "群創"},
    {"id": "3665", "name": "贸聯-KY"},
    {"id": "8358", "name": "金居"},
    {"id": "6443", "name": "晶技"},
    {"id": "2308", "name": "台達電"},
    {"id": "3711", "name": "日月光投控"},
    {"id": "2327", "name": "國巨"},
]

API_BASE = "https://api.finmindtrade.com/api/v4/data"

# ── FinMind API ──────────────────────────────────────────
def fetch_revenue(stock_id: str) -> list:
    """從 FinMind 抓月營收，回傳 list of {month, revenue, year}"""
    url = f"{API_BASE}?dataset=TaiwanStockMonthRevenue&data_id={stock_id}&start_date=2025-01-01&end_date=2026-12-31"
    try:
        r = requests.get(url, timeout=20)
        d = r.json()
        raw = d.get("data", [])
        # FinMind revenue 單位是元，Yahoo 是仟元 → 除以 1000
        records = []
        for item in raw:
            records.append({
                "year": item.get("revenue_year"),
                "month": item.get("revenue_month"),
                "revenue": int(item.get("revenue", 0)) // 1000,  # 仟元
            })
        # 按年月排序
        records.sort(key=lambda x: (x["year"], x["month"]))
        return records
    except Exception as e:
        print(f"  ⚠️ {stock_id} 抓取失敗: {e}")
        return []

# ── 計算月增率/年增率 ───────────────────────────────────
def compute_changes(records: list) -> list:
    """給予排序好的 records，附加 MoM / YoY"""
    if len(records) < 2:
        return records

    result = []
    for i, cur in enumerate(records):
        item = dict(cur)

        # 月增率（跟前一个月比）
        if i > 0:
            prev = records[i - 1]
            if prev["revenue"] > 0:
                item["mom"] = (cur["revenue"] - prev["revenue"]) / prev["revenue"] * 100
            else:
                item["mom"] = None
        else:
            item["mom"] = None

        # 年增率（跟前一年同月比）
        same_month_prev = next(
            (r for r in records if r["year"] == cur["year"] - 1 and r["month"] == cur["month"]),
            None
        )
        if same_month_prev and same_month_prev["revenue"] > 0:
            item["yoy"] = (cur["revenue"] - same_month_prev["revenue"]) / same_month_prev["revenue"] * 100
        else:
            item["yoy"] = None

        result.append(item)
    return result

# ── 格式化 Discord 表格 ─────────────────────────────────
def fmt_table(records_by_stock: list) -> str:
    """產生 Discord Markdown 表格"""
    lines = [
        "## 📊 持股月營收追蹤",
        "",
        "| 股票 | 代號 | 月份 | 營收（億）| 月增% | 年增% |",
        "|:---|:---|:---|:---|:---|:---|"
    ]
    for stock in records_by_stock:
        name = stock["name"]
        sid = stock["id"]
        recs = stock["records"]
        if not recs:
            lines.append(f"| {name} | {sid} | 無資料 | — | — | — |")
            continue
        # 最新一筆記錄
        cur = recs[-1]
        rev_b = cur["revenue"] / 1e5  # 仟元 → 億 (1e5 = 100,000 * 1000 / 1e9)
        mom_str = f"{cur['mom']:+.1f}%" if cur.get("mom") is not None else "—"
        yoy_str = f"{cur['yoy']:+.1f}%" if cur.get("yoy") is not None else "—"
        month_str = f"{cur['year']}/{cur['month']:02d}"
        lines.append(f"| {name} | {sid} | {month_str} | {rev_b:.2f} | {mom_str} | {yoy_str} |")

    return "\n".join(lines)

# ── 產生 LLM 分析 block ─────────────────────────────────
def build_llm_block(records_by_stock: list) -> str:
    lines = ["【持股月營收資料】\n"]
    for stock in records_by_stock:
        name = stock["name"]
        sid = stock["id"]
        recs = stock["records"]
        if not recs:
            lines.append(f"{name}({sid})：無資料")
            continue
        # 最近3筆
        recent = recs[-3:]
        lines.append(f"**{name}({sid})**：")
        for r in recent:
            rev_b = r["revenue"] / 1e5
            mom_str = f"{r['mom']:+.1f}%" if r.get("mom") is not None else "N/A"
            yoy_str = f"{r['yoy']:+.1f}%" if r.get("yoy") is not None else "N/A"
            lines.append(f"  {r['year']}/{r['month']:02d} 營收 {rev_b:.2f} 億（MoM {mom_str}, YoY {yoy_str}）")
        lines.append("")
    return "\n".join(lines)

# ── LLM 分析 ────────────────────────────────────────────
def load_env_key():
    """從 stockdev_config 取得 MINIMAX_API_KEY（不再硬編碼）"""
    return get_secret("MINIMAX_API_KEY")

def llm_analyze(block: str) -> str:
    api_key = load_env_key()
    api_url = "https://api.minimax.io/v1/chat/completions"

    prompt = f"""你是台股分析師。以下是持股的月營收資料（單位：億新台幣）：

{block}

請分析：
1. 哪些公司最新一個月營收表現亮眼（MoM 或 YoY 成長明顯）？
2. 哪些公司需要留意（衰退或低於預期）？
3. 簡短重點摘要（3-5句話）。

回覆時用 Discord Markdown，開頭加「## 📈 月營收 AI 分析」，直接給分析內容，不需要格式裝飾。"""

    try:
        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "MiniMax-M3", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
            timeout=60
        )
        result = resp.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"]
        else:
            return f"⚠️ LLM 分析失敗：{result}"
    except Exception as e:
        return f"⚠️ LLM 分析失敗：{e}"

# ── Discord 發送（分段 content 格式）─────────────────────
def send_discord(title: str, content: str):
    import urllib.request
    import json as _json

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }

    # 分段：Discord embed description 上限 4096，content 上限 2000
    # 改用 content 欄位，每段 1900 字
    MAX_LEN = 1900
    chunks = []
    while len(content) > MAX_LEN:
        chunks.append(content[:MAX_LEN])
        content = content[MAX_LEN:]
    chunks.append(content)

    # 先發標題
    header_payload = _json.dumps({"content": "**" + title}).encode()
    req = urllib.request.Request(DISCORD_WEBHOOK, data=header_payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 204:
                print(f"⚠️ Discord 標題發送響應: {resp.status}")
    except Exception as e:
        print(f"⚠️ Discord 標題發送失敗: {e}")

    import time
    time.sleep(0.3)

    # 發送內容段落
    for i, chunk in enumerate(chunks):
        payload = _json.dumps({"content": chunk}).encode()
        req = urllib.request.Request(DISCORD_WEBHOOK, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 204:
                    print(f"⚠️ Discord 段落{i+1}發送響應: {resp.status}")
        except Exception as e:
            print(f"⚠️ Discord 段落{i+1}發送失敗: {e}")
        time.sleep(0.3)

    print(f"✅ Discord 發送成功（共 {len(chunks)+1} 段）")

# ── 儲存本地 ────────────────────────────────────────────
def save_report(block: str, table: str, llm_result: str, all_records: list):
    import os
    out_dir = os.path.expanduser("~/.hermes/profiles/stock-dev/cron/output")
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")

    md = f"# 月營收報告 — {today}\n\n{table}\n\n---\n\n## LLM 分析\n\n{llm_result}\n\n---\n\n## 原始資料\n\n{block}"

    path = os.path.join(out_dir, f"revenue_{today}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"📁 報告已儲存: {path}")

    # 也存一份 JSON 快取
    cache_dir = "/Volumes/AI_Drive/StockData_v2/data"
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "revenue_cache.json")
    cache_data = {
        "updated": today,
        "stocks": {s["id"]: {"name": s["name"], "records": s["records"]} for s in all_records}
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    print(f"📦 快取已儲存: {cache_path}")

# ── 主程式 ──────────────────────────────────────────────
def main(mode="full"):
    print(f"📊 月營收報告 [{mode.upper()}] — {datetime.now().strftime('%Y/%m/%d %H:%M')}")
    print(f"共 {len(STOCKS)} 檔股票\n")

    all_records = []
    for s in STOCKS:
        print(f"抓取 {s['name']}({s['id']}) ...", end=" ", flush=True)
        raw = fetch_revenue(s["id"])
        if raw:
            records = compute_changes(raw)
            all_records.append({"id": s["id"], "name": s["name"], "records": records})
            cur = records[-1]
            rev_b = cur["revenue"] / 1e5
            print(f"✓ {cur['year']}/{cur['month']:02d} {rev_b:.2f} 億")
        else:
            all_records.append({"id": s["id"], "name": s["name"], "records": []})
            print("⚠️ 無資料")
        time.sleep(0.5)

    # 只取有資料的股票
    available = [r for r in all_records if r["records"]]
    available_ids = [r["id"] for r in available]

    if mode == "partial":
        # ── 8號/9號口語回報 ───────────────────────────────
        print(f"\n--- 口語回報（已揭露 {len(available)}/{len(STOCKS)} 間）---")
        latest_month = max((r["records"][-1] for r in available),
                            key=lambda x: (x["year"], x["month"]))
        latest_ym = f"{latest_month['year']}/{latest_month['month']:02d}"
        lines = [f"📊 月營收快報 — 截至今天 {len(available)} 間公司已揭露 {latest_ym} 營收：\n"]
        for r in available:
            cur = r["records"][-1]
            rev_b = cur["revenue"] / 1e5
            mom = cur.get("mom")
            yoy = cur.get("yoy")
            mom_str = f"{mom:+.1f}%" if mom is not None else "N/A"
            yoy_str = f"{yoy:+.1f}%" if yoy is not None else "N/A"
            lines.append(f"• {r['name']}({r['id']})：{rev_b:.2f} 億 | 月增 {mom_str} | 年增 {yoy_str}")

        not_yet = [s["name"] for s in STOCKS if s["id"] not in available_ids]
        if not_yet:
            lines.append(f"\n⏳ 尚未揭露：{', '.join(not_yet)}")

        casual = "\n".join(lines)
        print(casual)
        print("\n--- 發送 Discord ---")
        send_discord("📊 月營收快報（FinMind）", casual)
        return

    # ── 10號完整分析 ──────────────────────────────────────
    print("\n--- 格式化表格 ---")
    table = fmt_table(all_records)
    print(table)

    print("\n--- LLM 分析 ---")
    llm_block = build_llm_block(all_records)
    llm_result = llm_analyze(llm_block)
    print(llm_result[:300] if llm_result else "無")

    print("\n--- 發送 Discord ---")
    full = f"{table}\n\n{'─'*40}\n\n✨ *以下為 AI 分析結果*\n\n{llm_result}"
    send_discord("📊 月營收報告（FinMind 快取）", full)

    save_report(llm_block, table, llm_result, all_records)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode in ("discord", "full"):
            main("full")
        elif mode == "partial":
            main("partial")
        else:
            print("用法: python3 revenue_report.py [partial|full|discord]")
    else:
        main("full")
