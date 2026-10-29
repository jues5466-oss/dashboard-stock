#!/usr/bin/env python3
"""
台指期貨未平倉分析報告（下午 18:00 發送）
撈取：外资/自營商/投信 未平倉口數 + 全市場總口數
分析：淨多單變化 → 市場意涵 → 操作建議
"""

import urllib.request
import json
import re
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trading_calendar import is_trading_day, holiday_reason
from stockdev_config import get_secret

# ── 設定區 ──────────────────────────────────────────
API_KEY = get_secret("MINIMAX_API_KEY")
API_URL  = "https://api.minimax.io/v1/chat/completions"
MODEL    = "MiniMax-M3"

DISCORD_WEBHOOK = get_secret("DISCORD_WEBHOOK_OI")

# TAIFEX API
BASE_URL = "https://www.taifex.com.tw/cht/quotesApi/getQuotes"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.taifex.com.tw/cht/index",
    "X-Requested-With": "XMLHttpRequest",
}


# ── TWSE T86 API（當日現貨三大法人買賣超）──────────
def fetch_t86_summary() -> dict:
    """
    抓取當日三大法人現貨買賣超金額（全市場合計）。
    欄位 row[4/10/11/18] 是股數，乘以均價 100 元轉為百萬元，再轉億元。
    """
    import ssl
    from datetime import datetime
    today = datetime.now().strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={today}&response=json&selectType=ALL"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            d = json.loads(r.read().decode())
            if d.get("stat") != "OK":
                return {"error": f"API stat={d.get('stat')}"}

            total_foreign = 0
            total_prop = 0
            total_dealer = 0
            total_all = 0
            for row in d.get("data", []):
                try:
                    total_foreign += int(row[4].replace(",", ""))
                    total_prop    += int(row[10].replace(",", ""))
                    total_dealer  += int(row[11].replace(",", ""))
                    total_all     += int(row[18].replace(",", ""))
                except (ValueError, IndexError):
                    continue

            # 股數 → 百萬元（假設均價 100 元，100 股 = 1 張 = 1 萬元）
            # 百萬元 = 股數 * 100 / 1,000,000
            to_億 = lambda shares: round(shares * 100 / 1e8, 1)

            return {
                "date": today,
                "foreign_億": to_億(total_foreign),
                "prop_億":    to_億(total_prop),
                "dealer_億": to_億(total_dealer),
                "total_億":  to_億(total_all),
                "_raw": {"foreign": total_foreign, "prop": total_prop,
                         "dealer": total_dealer, "total": total_all},
            }
    except Exception as e:
        return {"error": str(e)}


# ── TAIFEX API ─────────────────────────────────────
def fetch_taifex(objId: str) -> list:
    ts = str(int(__import__("time").time() * 1000))
    url = f"{BASE_URL}?objId={objId}&_={ts}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_oi_data() -> dict:
    """取得三大法人未平倉口數（前一日 vs 前前日）"""
    result = {}

    # 三大法人 OI
    for oid, key, label in [
        ("10", "foreign",  "外商（含陸資）"),
        ("6",  "dealer",   "自營商"),
        ("8",  "fund",     "投信"),
    ]:
        try:
            raw = fetch_taifex(oid)
            # 取最新 2 筆（倒序）
            entries = [(d["Date"], int(d["value"])) for d in raw]
            entries.sort()
            latest  = entries[-1]   # (date, oi_latest)
            prev    = entries[-2] if len(entries) >= 2 else (None, None)
            # 昨天變化 = 最新 - 前一天（正=多單增加 or 空單減少）
            change  = latest[1] - prev[1] if prev[1] is not None else None
            result[key] = {
                "label":    label,
                "oi_latest": latest[1],
                "change":   change,     # 正=對多方有利
                "date":     latest[0],
            }
        except Exception as e:
            result[key] = {"label": label, "error": str(e)}

    # 全市場期貨總口數
    try:
        data   = fetch_taifex("1")
        futvol = data[0]["futvol"].replace(",", "")
        result["total_market"] = {"futvol": int(futvol)}
    except Exception as e:
        result["total_market"] = {"error": str(e)}

    return result


# ── 格式化 ─────────────────────────────────────────
def fmt_oi_block(data: dict, t86: dict = None) -> str:
    foreign = data.get("foreign", {})
    dealer  = data.get("dealer", {})
    fund    = data.get("fund", {})
    total   = data.get("total_market", {}).get("futvol", None)

    f_oi  = foreign.get("oi_latest", 0) or 0
    f_chg = foreign.get("change")
    d_oi  = dealer.get("oi_latest", 0) or 0
    d_chg = dealer.get("change")
    u_oi  = fund.get("oi_latest", 0) or 0
    u_chg = fund.get("change")

    sign = lambda x: "+" if x and x >= 0 else ""

    lines = ["【台指期貨未平倉分析】（收盤後）"]
    lines.append("")

    # 原始數據
    for key, label, oi, chg in [
        ("foreign", "外商（含陸資）", f_oi, f_chg),
        ("dealer",  "自營商",        d_oi, d_chg),
        ("fund",    "投信",          u_oi, u_chg),
    ]:
        if oi is None:
            lines.append(f"• {label}：資料取得失敗")
        else:
            chg_s = f"（日變化 {sign(chg)}{chg:,} 口）" if chg is not None else ""
            lines.append(f"• {label}：{oi:,} 口 {chg_s}")

    if total:
        lines.append(f"• 全市場期貨總口數：{total:,} 口")

    lines.append("")
    lines.append("【現貨三大法人買賣超】（當日）")
    if t86 and "error" not in t86:
        f_億 = t86.get("foreign_億", 0)
        p_億 = t86.get("prop_億", 0)
        d_億 = t86.get("dealer_億", 0)
        t_億 = t86.get("total_億", 0)
        sign = lambda x: "+" if x >= 0 else ""
        lines.append(f"• 外資（含陸資）：{sign(f_億)}{f_億:.1f} 億")
        lines.append(f"• 投信：{sign(p_億)}{p_億:.1f} 億")
        lines.append(f"• 自營商：{sign(d_億)}{d_億:.1f} 億")
        lines.append(f"• 三大法人合計：{sign(t_億)}{t_億:.1f} 億")
    elif t86 and "error" in t86:
        lines.append(f"  （T86 資料取得失敗：{t86['error']}）")
    else:
        lines.append("  （無資料）")

    lines.append("")
    lines.append("【三大法人動向】")

    # 外資判斷
    if f_chg is not None:
        if f_chg > 0:
            f_desc = f"持有{f_oi:,} 口淨空單，日變化 {sign(f_chg)}{f_chg:,} 口 — **空單回補，多方力道增強**"
        else:
            f_desc = f"持有{f_oi:,} 口淨空單，日變化 {sign(f_chg)}{f_chg:,} 口 — 空單增加，偏空看待"
    else:
        f_desc = f"持有{f_oi:,} 口淨空單（無日變化資料）"
    lines.append(f"• 外資（含陸資）：{f_desc}")

    # 自營商判斷
    if d_chg is not None:
        if d_chg > 0:
            d_desc = f"{d_oi:,} 口淨多單，日變化 {sign(d_chg)}{d_chg:,} 口 — **由空轉多，短線轉向樂觀**"
        elif d_chg < 0:
            d_desc = f"{d_oi:,} 口淨多單，日變化 {sign(d_chg)}{d_chg:,} 口 — 多單減少，偏空看待"
        else:
            d_desc = f"{d_oi:,} 口淨多單，日變化持平"
    else:
        d_desc = f"{d_oi:,} 口淨多單（無日變化資料）"
    lines.append(f"• 自營商：{d_desc}")

    # 投信判斷
    if u_chg is not None:
        if u_chg < 0:
            u_desc = f"{u_oi:,} 口淨多單，日變化 {sign(u_chg)}{u_chg:,} 口 — **略為減碼，但方向不變**"
        elif u_chg > 0:
            u_desc = f"{u_oi:,} 口淨多單，日變化 {sign(u_chg)}{u_chg:,} 口 — 持續加碼多方"
        else:
            u_desc = f"{u_oi:,} 口淨多單，日變化持平"
    else:
        u_desc = f"{u_oi:,} 口淨多單（無日變化資料）"
    lines.append(f"• 投信：{u_desc}")

    lines.append("")
    lines.append("【短線操作建議】")

    # 綜合判斷
    bullish = 0
    if f_chg and f_chg > 0: bullish += 1
    if d_chg and d_chg > 0: bullish += 1
    if u_chg and u_chg > 0: bullish += 1
    if f_oi < 0 and f_chg and f_chg > 0: bullish += 1  # 外資空單回補額外加分

    if bullish >= 3:
        lines.append("今晚結算多方占優，明日開盤**偏多看待** 📈")
    elif bullish == 2:
        lines.append("多方略占上風，**觀望偏多**")
    elif bullish == 1:
        lines.append("多空拉扯，建議**觀望**為主")
    else:
        lines.append("空方力道較強，**保守因應**")

    return "\n".join(lines)


# ── LLM 分析 ────────────────────────────────────────
def llm_analyze(oi_block: str) -> str:
    system_prompt = """你是一個專業的台灣期貨市場分析師。
根據以下三大法人未平倉口數資料，進行分析：

三大法人身份說明：
- 外資及陸資：代表國際機構投資者，對台股有主導性影響力
- 自營商：同時做多做空，視為「中性」；若淨多單大幅增加，可能反映避險需求上升
- 投信：代表本土機構投資者，通常偏多操作

分析重點：
1. 外資淨多單（OI）變化的方向與幅度 → 對台股後市的指示意義
2. 自營商淨多單方向 → 反映自營商對短線盤勢的判斷（避險or投機）
3. 散戶淨多單 = 全市場 - 外資 - 投信 - 自營商（自營商口數中約當散戶部分）→ 反向指標參考
4. 全市場總口數變化 → 期貨市場散場或進場的溫度計

輸出格式（正體中文，簡潔有力）：
【三大法人動向】
（3-5句，用數據說故事）

【散戶反向指標觀察】
（2-3句，散戶淨多單是增加還是減少？過熱or過冷？）

【短線操作建議】
（3句，給出方向性建議：偏多/偏空/觀望 + 理由）

如有口數為負值，請特別說明「淨空單」並解讀其意涵。"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",    "content": f"以下是台指期貨未平倉數據：\n\n{oi_block}"},
        ],
        "max_tokens": 1200,
        "temperature": 0.3,
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.loads(resp.read().decode())
            return d["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ LLM 分析失敗：{e}"


# ── Discord ────────────────────────────────────────
def send_discord(text: str) -> bool:
    chunks = []
    while len(text) > 1900:
        chunks.append(text[:1900])
        text = text[1900:]
    chunks.append(text)

    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    for chunk in chunks:
        payload = json.dumps({"content": chunk}).encode()
        req = urllib.request.Request(DISCORD_WEBHOOK, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 204:
                    print(f"   ⚠️ Discord: {resp.status}")
        except Exception as e:
            print(f"   ❌ Discord 失敗：{e}")
            return False
    return True


# ── 主程式 ─────────────────────────────────────────
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "local"

    # 休市日直接跳過（避免用舊資料冒充當日數據）
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not is_trading_day(today_str):
        reason = holiday_reason(today_str)
        print(f"⏭️  今日休市（{reason}），跳過台指期貨未平倉分析，不發送 Discord。")
        return

    print("🔍 抓取台指期貨未平倉數據...")
    oi_data = get_oi_data()

    print("🔍 抓取現貨三大法人買賣超（T86）...")
    t86_data = fetch_t86_summary()
    if "error" in t86_data:
        print(f"   ⚠️ T86: {t86_data['error']}")
    else:
        f_億 = t86_data.get("foreign_億", 0)
        p_億 = t86_data.get("prop_億", 0)
        d_億 = t86_data.get("dealer_億", 0)
        t_億 = t86_data.get("total_億", 0)
        sign = lambda x: "+" if x >= 0 else ""
        print(f"   • 外資：{sign(f_億)}{f_億:.1f} 億")
        print(f"   • 投信：{sign(p_億)}{p_億:.1f} 億")
        print(f"   • 自營商：{sign(d_億)}{d_億:.1f} 億")
        print(f"   • 合計：{sign(t_億)}{t_億:.1f} 億")

    for k, d in oi_data.items():
        if k == "total_market":
            print(f"   • 全市場：{d.get('futvol','N/A'):,} 口" if d.get("futvol") else f"   • 全市場：錯誤")
        else:
            oi  = d.get("oi_latest")
            chg = d.get("change")
            sign = "+" if chg and chg >= 0 else ""
            print(f"   • {d['label']}：{oi:,} 口（日變化 {sign}{chg:,} 口）" if chg is not None else f"   • {d.get('label','?')}：錯誤")

    oi_block = fmt_oi_block(oi_data, t86_data)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    md_lines = []
    md_lines.append(f"## 📊 台指期貨未平倉分析  `({now_str})`")
    md_lines.append("")
    md_lines.append(oi_block)
    md_report = "\n".join(md_lines)

    print("\n" + "=" * 60)
    print(md_report)

    out_path = "/tmp/oi_report.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"\n✅ 報告已存：{out_path}")

    if mode == "discord":
        print("\n📤 發送到 Discord...")
        ok = send_discord(md_report)
        print("✅ 成功" if ok else "❌ 失敗")

if __name__ == "__main__":
    main()
