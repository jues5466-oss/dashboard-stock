#!/usr/bin/env python3
"""
金融新聞爬蟲 + MiniMax LLM 分析 + Discord 推播
新結構（2026/08）：
1. 【國際市場數據】台指期、日經、韓股
2. 【美股昨夜收盤】S&P500、Nasdaq、VIX（CNBC 新聞僅供 LLM 分析用，不發 Discord）
3. 【美股期貨當前】NQ、ES
4. 【對台灣的影響】LLM 推理
5. 【當日重要新聞】台灣本地新聞
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import json
import os
import re
import sys
from datetime import datetime, timezone
import yfinance as yf
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trading_calendar import is_trading_day, holiday_reason
from stockdev_config import get_secret

# ── 設定區 ──────────────────────────────────────────
API_KEY = get_secret("MINIMAX_API_KEY")
API_URL = "https://api.minimax.io/v1/chat/completions"
MODEL   = "MiniMax-M3"

# RSS 來源
RSS_URL_TW  = "https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
RSS_URL_CNBC = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"

DISCORD_WEBHOOK = get_secret("DISCORD_WEBHOOK_FINANCE")

# 過濾台灣新聞的關鍵字
KEYWORDS_TW = [
    "台股", "加權", "聯發科", "台積電", "航運", "鋼鐵",
    "台幣", "美元", "日幣", "匯率",
    "中國", "習近平", "川普", "拜登",
    "央行", "金管會", "櫃買", "上市",
    "AI", "半導體", "晶片", "輝達",
    "長榮", "陽明", "萬海",
    "中鋼",
    "軍工", "漢翔", "亞航",
    "金融", "銀行", "壽險", "證券",
    "比特幣", "加密", "虛擬貨幣",
    "油價", "能源", "OPEC",
    "通膨", "CPI", "物價",
    "GDP", "景氣", "經濟",
    "地震", "颱風", "天災",
    "缺電", "水荒",
    "法說", "財報", "EPS",
    "紅鏈", "脫鉤",
    "護國神山", "供應鏈",
]

# ── 時間工具 ────────────────────────────────────────
def parse_rss_date(date_str: str):
    from email.utils import parsedate_to_datetime
    return parsedate_to_datetime(date_str)

def time_ago(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    diff = now - dt
    h = diff.total_seconds() / 3600
    if h < 1:
        return f"{int(diff.total_seconds()/60)}分鐘前"
    elif h < 24:
        return f"{int(h)}小時前"
    else:
        return f"{int(h/24)}天前"

def is_relevant_tw(title: str, desc: str = "") -> bool:
    text = (title + " " + desc).lower()
    return any(kw.lower() in text for kw in KEYWORDS_TW)

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)

# ── 官方收盤資料（LLM 數字事實基準）──────────────────
DATA_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "daily_data")


def latest_daily_csvs(n: int = 2) -> list:
    """回傳最近 n 個交易日的 CSV 路徑（由新到舊）。"""
    try:
        years = sorted((d for d in os.listdir(DATA_ROOT) if d.isdigit()), reverse=True)
    except Exception:
        return []
    out = []
    for y in years:
        ydir = os.path.join(DATA_ROOT, y)
        try:
            files = sorted((f for f in os.listdir(ydir) if f.endswith(".csv")), reverse=True)
        except Exception:
            continue
        for f in files:
            out.append(os.path.join(ydir, f))
            if len(out) >= n:
                return out
    return out


def _ymd(fname: str) -> str:
    """20261028 → 2026-10-28"""
    d = os.path.basename(fname)[:-4]
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d


def read_2330_close(path: str):
    """從單一 CSV 讀出 2330 的收盤價。"""
    try:
        import csv as _csv
        with open(path, encoding="utf-8-sig") as f:
            for row in _csv.DictReader(f):
                if str(row.get("code", "")).strip() == "2330":
                    return float(row["close"])
    except Exception:
        return None
    return None


def get_tsmc_ground_truth() -> str:
    """台積電官方收盤（最近兩個交易日），作為 LLM 的數字事實基準。

    沒有這段時 LLM 只能從新聞標題抓數字，會把兩則不同新聞的數字串接
    （2026/10/29 實測產生「下跌35元至25元」）。
    """
    files = latest_daily_csvs(2)
    if not files:
        return "（無官方收盤資料）"
    cur = read_2330_close(files[0])
    prev = read_2330_close(files[1]) if len(files) > 1 else None
    if cur is None:
        return "（無官方收盤資料）"
    if prev is None:
        return f"台積電（2330）{_ymd(files[0])} 收盤 {cur}（前一交易日資料缺漏）"
    chg = cur - prev
    pct = chg / prev * 100 if prev else 0.0
    return (f"台積電（2330）{_ymd(files[0])} 收盤 {cur}，"
            f"較 {_ymd(files[1])} 收盤 {prev} 變動 {chg:+} 元（{pct:+.2f}%）")


# ── 交易時段狀態（決定報告語態）───────────────────────
def market_session_state(now=None) -> tuple:
    """回傳 (state, description)。

    state: pre_open（未開盤）/ intraday（盤中）/ closed（已收盤或休市）
    """
    now = now or datetime.now()
    hm = now.hour * 60 + now.minute
    if now.weekday() >= 5:
        return "closed", f"今天是週{'六日'[now.weekday() - 5]}，台股休市"
    if hm < 9 * 60:
        return "pre_open", f"現在 {now:%H:%M}，台股尚未開盤（09:00 開盤）"
    if hm < 13 * 60 + 30:
        return "intraday", f"現在 {now:%H:%M}，台股盤中（09:00-13:30）"
    return "closed", f"現在 {now:%H:%M}，台股今日已收盤（13:30 收盤）"


# ── 數字矛盾修補 ────────────────────────────────────
# 「下跌35元至25元」＝ 把兩則不同新聞的漲跌金額拼在一起
_CONTRADICT_RE = re.compile(
    r"(?P<verb>下跌|大跌|重挫|挫跌|跌|滑落|回落|上漲|大漲|上揚|飆漲|漲)"
    r"\s*(?P<v1>\d[\d,]*\.?\d*)\s*元"
    r"\s*(?:至|到|~|～)\s*"
    r"(?P<v2>\d[\d,]*\.?\d*)\s*元"
)


def sanitize_contradictions(text: str) -> tuple:
    """修正「同一句話裡同一標的出現兩個不同漲跌金額」的拼接錯誤。

    回傳 (修正後文字, 修正清單)。
    """
    fixed = []

    def _repl(m):
        v1 = float(m.group("v1").replace(",", ""))
        v2 = float(m.group("v2").replace(",", ""))
        if v1 == v2:
            return m.group(0)
        fixed.append(f"{m.group('verb')}{m.group('v1')}元至{m.group('v2')}元")
        return f"{m.group('verb')}{m.group('v1')}元"

    return _CONTRADICT_RE.sub(_repl, text), fixed

# ── RSS 抓取 ────────────────────────────────────────
def fetch_rss(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; FinanceBot/1.0)",
        "Accept-Encoding": "gzip, deflate",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()

def parse_rss(data: bytes) -> list[dict]:
    import gzip
    try:
        content = gzip.decompress(data)
    except Exception:
        content = data

    root = ET.fromstring(content)
    items = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el  = item.find("link")
        pub_el   = item.find("pubDate")
        desc_el  = item.find("description")
        guid_el  = item.find("guid")

        title    = title_el.text.strip() if title_el is not None and title_el.text else ""
        link     = link_el.text.strip()  if link_el  is not None and link_el.text  else ""
        pub_str  = pub_el.text.strip()  if pub_el   is not None and pub_el.text   else ""
        desc_raw = desc_el.text if desc_el is not None and desc_el.text else ""
        guid     = guid_el.text if guid_el is not None and guid_el.text else link

        pub_dt = parse_rss_date(pub_str)
        desc   = strip_html(desc_raw)[:200]

        items.append({
            "title": title,
            "link":  link,
            "pub":   pub_dt,
            "ago":   time_ago(pub_dt),
            "desc":  desc,
            "guid":  guid,
        })
    return items

# ── 美股昨夜收盤（S&P500、Nasdaq、VIX）─────────────
def get_us_closes() -> dict:
    """抓取美股三大指數昨夜收盤"""
    result = {}
    for symbol, key, label in [
        ("^GSPC", "sp500",  "S&P 500"),
        ("^IXIC", "nasdaq", "Nasdaq"),
        ("^SOX",  "sox",    "費城半導體"),
        ("^VIX",  "vix",    "VIX"),
    ]:
        try:
            data = yf.download(symbol, period="5d", auto_adjust=True, progress=False)
            vals = data["Close"].values.flatten()
            valid = vals[~np.isnan(vals)]
            if len(valid) < 2:
                result[key] = {"label": label, "close": "休市", "pct": None}
            else:
                curr = float(valid[-1])
                prev = float(valid[-2])
                pct  = (curr - prev) / prev * 100
                result[key] = {
                    "label": label,
                    "close": round(curr, 2),
                    "change": round(curr - prev, 2),
                    "pct":   round(pct, 2),
                }
        except Exception as e:
            result[key] = {"label": label, "close": "取得失敗", "change": None, "pct": None}
    return result

# ── 美股期貨（NQ、ES）───────────────────────────────
def get_us_futures() -> dict:
    """
    抓取美股期貨盤後報價。
    用 1d+1m 取盤後交易時段（00:00 ET 起）的最新報價，
    對比當日日K收盤結算價，計算盤後真正的漲跌。
    """
    result = {}
    for symbol, key, label in [
        ("NQ=F", "nasdaq100_f", "小型納斯達克（NQ）"),
        ("ES=F", "sp500_f",     "小型S&P 500（ES）"),
    ]:
        try:
            # 當日日K收盤結算價
            daily = yf.download(symbol, period="5d", auto_adjust=True, progress=False)
            daily_vals = daily["Close"][symbol].values
            daily_vals = daily_vals[~np.isnan(daily_vals)]
            prev_close = float(daily_vals[-2])   # 前一晚收盤（對比基準）
            today_settle = float(daily_vals[-1])  # 當日結算（參考用）

            # 盤後交易時段最新報價（1m，亞洲早上8:20能拿到盤後最新報價）
            intraday = yf.download(symbol, period="1d", interval="1m", auto_adjust=True, progress=False)
            intraday_vals = intraday["Close"][symbol].values
            intraday_vals = intraday_vals[~np.isnan(intraday_vals)]

            if len(intraday_vals) < 1:
                # 盤後無資料（週末/假日），用日K收盤
                curr = today_settle
                pct = 0.0
            else:
                curr = float(intraday_vals[-1])
                # 盤後漲跌：相對於前一晚收盤（用戶真正想看的「今晚是漲是跌」）
                pct = (curr - prev_close) / prev_close * 100

            result[key] = {
                "label": label,
                "close": round(curr, 2),
                "change": round(curr - prev_close, 2),
                "pct":   round(pct, 2),
            }
        except Exception as e:
            result[key] = {"label": label, "close": "取得失敗", "change": None, "pct": None}
    return result
def get_market_data() -> dict:
    """抓取台指期夜盤、日經、韓股"""
    results = {}

    # 台指期夜盤 — Yahoo 奇摩期貨頁面（2026/08 結構已改用 price-detail-list）
    try:
        tx_url = "https://tw.stock.yahoo.com/future/WTX%26"
        req = urllib.request.Request(tx_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode()

        # 解析 price-detail-item：成交=現價，昨收=前一日收盤
        # 2026/08 Yahoo 奇摩結構：開盤→買價→賣價→成交→...→昨收
        # 故分開抓，避免 findall 把開盤價誤當成交價
        curr_match = re.search(r'<span[^>]*>成交</span><span[^>]*>([\d,]+)\.00</span>', html)
        prev_match = re.search(r'<span[^>]*>昨收</span><span[^>]*>([\d,]+)\.00</span>', html)
        if curr_match and prev_match:
            curr = float(curr_match.group(1).replace(",", ""))
            prev = float(prev_match.group(1).replace(",", ""))
            chg  = curr - prev
            pct  = chg / prev * 100
            results["tx_night"] = {"close": curr, "change": chg, "pct": round(pct, 2)}
        elif curr_match:
            # 只有成交（可能昨收尚未更新），用成交價
            curr = float(curr_match.group(1).replace(",", ""))
            results["tx_night"] = {"close": curr, "change": 0.0, "pct": 0.0}
        else:
            results["tx_night"] = "解析失敗"
    except Exception as e:
        results["tx_night"] = f"取得失敗：{e}"

    # 日經 225
    try:
        data = yf.download("^N225", period="5d", auto_adjust=True, progress=False)
        vals = data["Close"].values.flatten()
        valid = vals[~np.isnan(vals)]
        if len(valid) >= 2:
            curr, prev = valid[-1], valid[-2]
            pct = (curr - prev) / prev * 100
            results["nikkei"] = {"close": round(curr, 2), "change": round(curr - prev, 2), "pct": round(pct, 2)}
        else:
            results["nikkei"] = "休市"
    except Exception as e:
        results["nikkei"] = f"取得失敗：{e}"

    # 韓國 KOSPI
    try:
        data = yf.download("^KS11", period="5d", auto_adjust=True, progress=False)
        vals = data["Close"].values.flatten()
        valid = vals[~np.isnan(vals)]
        if len(valid) >= 2:
            curr, prev = valid[-1], valid[-2]
            pct = (curr - prev) / prev * 100
            results["kospi"] = {"close": round(curr, 2), "change": round(curr - prev, 2), "pct": round(pct, 2)}
        else:
            results["kospi"] = "休市"
    except Exception as e:
        results["kospi"] = f"取得失敗：{e}"

    return results

# ── 格式化區塊 ──────────────────────────────────────
def fmt_market_block(data: dict) -> str:
    """【國際市場數據】台指期夜盤、日經、韓股

    取不到資料時必須把「解析失敗 / 取得失敗」原樣顯示出來。
    早期版本只在拿到 dict 時才加行，失敗會被靜默丟掉整行 →
    使用者看不到缺資料，LLM 也只能自己臆測（例如編出台指期夜盤走向）。
    """
    lines = ["【國際市場數據】"]
    for key, label in [("tx_night", "台指期夜盤"), ("nikkei", "日經 225"),
                       ("kospi", "韓國 KOSPI")]:
        d = data.get(key)
        if isinstance(d, dict):
            sign = "+" if d.get("pct", 0) >= 0 else ""
            lines.append(f"• {label}：{d['close']} ({d['change']:+}點 / {sign}{d['pct']}%)")
        else:
            lines.append(f"• {label}：{d or '無資料'}（資料不可用，禁止臆測數字）")
    return "\n".join(lines)

def fmt_us_close_block(us: dict, cnbc_news: list) -> str:
    """【美股昨夜收盤】+ CNBC 新聞（用於 LLM 分析）"""
    lines = ["【美股昨夜收盤】"]
    for key, label in [("sp500","S&P 500"), ("nasdaq","Nasdaq"), ("sox","費城半導體"), ("vix","VIX")]:
        d = us.get(key, {})
        if isinstance(d.get("close"), (int, float)):
            sign = "+" if d["pct"] >= 0 else ""
            lines.append(f"• {label}：{d['close']} ({d['change']:+}點 / {sign}{d['pct']}%)")
        else:
            lines.append(f"• {label}：{d.get('close','N/A')}")
    if cnbc_news:
        lines.append("")
        lines.append("─── CNBC 美股新聞 ───")
        for i, it in enumerate(cnbc_news[:8], 1):
            lines.append(f"{i}. {it['title']}（{it['ago']}）")
    return "\n".join(lines)

def fmt_us_close_block_discord(us: dict) -> str:
    """【美股昨夜收盤】（無 CNBC 新聞，用於 Discord）"""
    lines = ["【美股昨夜收盤】"]
    for key, label in [("sp500","S&P 500"), ("nasdaq","Nasdaq"), ("sox","費城半導體"), ("vix","VIX")]:
        d = us.get(key, {})
        if isinstance(d.get("close"), (int, float)):
            sign = "+" if d["pct"] >= 0 else ""
            lines.append(f"• {label}：{d['close']} ({d['change']:+}點 / {sign}{d['pct']}%)")
        else:
            lines.append(f"• {label}：{d.get('close','N/A')}")
    return "\n".join(lines)

def fmt_us_futures_block(futures: dict) -> str:
    """【美股期貨當前】"""
    lines = ["【美股期貨當前】"]
    for key, label in [("nasdaq100_f","小型納斯達克（NQ）"), ("sp500_f","小型S&P 500（ES）")]:
        d = futures.get(key, {})
        if isinstance(d.get("close"), (int, float)):
            sign = "+" if d["pct"] >= 0 else ""
            lines.append(f"• {label}：{d['close']} ({d['change']:+}點 / {sign}{d['pct']}%)")
        else:
            lines.append(f"• {label}：{d.get('close','N/A')}")
    return "\n".join(lines)

# ── LLM 分析（對台灣的影響）─────────────────────────
def strip_think(text: str) -> str:
    """移除 MiniMax M3 的思考區塊。

    M3 會把 reasoning 以 <think>...</think> 形式塞在 content 裡面
    （舊版 API 用 <thought>...</thought>），兩種都要清掉，
    且要處理未閉合的 <think>（思考被 max_tokens 截斷）。
    """
    if not text:
        return ""
    text = re.sub(r"<(think|thought)>[\s\S]*?</\1>", "", text, flags=re.IGNORECASE)
    # 未閉合的思考區塊：截斷到 <think> 之後全部丟棄
    text = re.sub(r"<(think|thought)>[\s\S]*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def strip_english_lines(text: str) -> str:
    """移除殘留的純英文思考句（保留含中文的行）。"""
    if not text:
        return ""
    out = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and not re.search(r"[\u4e00-\u9fff]", stripped):
            # 純 ASCII 行且看起來像英文敘述（多個英文單字、句號）
            if len(re.findall(r"[A-Za-z]{2,}", stripped)) >= 5:
                continue
        # 中英夾雜殘留，例如「搶_bottom」→ 移除底線片段
        line = re.sub(r"_([A-Za-z]+)", "", line)
        out.append(line)
    return "\n".join(out).strip()


def split_sections(text: str) -> dict:
    """把 LLM 分析依【...】標題切成 {標題: 內容}。

    注意：像「【重點新聞解析】」這種父標題後面緊接著「【重點新聞 A】」時，
    父標題自己的內容是空的，真正的內容在子標題底下。
    因此父標題的內容會自動把所有子標題（重點新聞 A/B/C…）一併接上。
    """
    if not text:
        return {}
    parts = re.split(r"【([^】]+)】", text)
    titles = [parts[i].strip() for i in range(1, len(parts) - 1, 2)]
    bodies = [parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)]

    sec = {t: b for t, b in zip(titles, bodies)}
    # 父標題 → 附加其後的子標題內容
    # 結構為：【重點新聞解析】→【重點新聞 A】→【重點新聞 B】…
    # 父標題本身沒有內容，實際內容在子標題底下，因此把子標題接回父標題。
    for i, t in enumerate(titles):
        if not re.match(r"^重點新聞\s+[A-Z0-9]+$", t):
            continue
        # 往前找最近一個「非子標題」的父標題
        parent = None
        for j in range(i - 1, -1, -1):
            if not re.match(r"^重點新聞\s+[A-Z0-9]+$", titles[j]):
                parent = titles[j]
                break
        if not parent:
            continue
        block = f"【{t}】\n{bodies[i]}".strip()
        sec[parent] = (sec.get(parent, "") + "\n\n" + block).strip()
    return sec


def call_llm(system_prompt: str, user_prompt: str,
             max_tokens: int = 8000, temperature: float = 0.3) -> tuple:
    """呼叫 MiniMax-M3。

    回傳 (ok, content, err_kind, err_msg)：
      - ok=True  → content 是乾淨的分析文字
      - ok=False → err_kind 為 "sensitive"（HTTP 422 內容審查）或 "other"

    HTTP 422 "input new_sensitive" 是 MiniMax 的輸入側內容審查：
    只要 prompt 內含某則被判定敏感的標題，整次請求就會被整包拒絕，
    連其他無關新聞都會一起被犧牲（2006/10/24 實測）。
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",    "content": user_prompt},
        ],
        # MiniMax-M3 預設開啟 thinking，reasoning token 算進 max_tokens，
        # 若額度不夠會 finish_reason=length 且 content 為空（只有思考沒有分析）。
        # thinking.type=disabled 可讓 M3 跳過思考直接作答（實測有效）。
        # reasoning_split=true 讓思考內容獨立到 reasoning_content，不混入 content。
        "max_tokens": max_tokens,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
        "reasoning_split": True,
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
        with urllib.request.urlopen(req, timeout=300) as resp:
            d = json.loads(resp.read().decode())
        msg = d["choices"][0]["message"]
        raw = msg.get("content") or ""
        # MiniMax M3 把 reasoning 放在 content 內的 <think>...</think>
        raw = strip_think(raw)
        if not raw.strip():
            return False, "", "empty", "LLM 只回傳思考過程，未產生正式分析"
        return True, raw.strip(), None, None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        if e.code == 422:
            return False, "", "sensitive", f"HTTP 422 內容審查拒絕: {body}"
        return False, "", "other", f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, "", "other", f"{type(e).__name__}: {e}"


def probe_sensitive(tw_list: list) -> bool:
    """用極簡 prompt 測試這批新聞是否會觸發 MiniMax 內容審查（HTTP 422）。

    用便宜的探測 prompt（只要一句摘要）而非完整分析 prompt，
    可大幅降低二分搜尋的 token 成本。回傳 True 代表「這批之中有敏感項」。
    """
    if not tw_list:
        return False
    text = "\n".join(f"{i}. {it['title']}" for i, it in enumerate(tw_list, 1))
    probe_sys = "你是新聞分類助手。請用一句話摘要以下標題。"
    ok, _raw, kind, _msg = call_llm(probe_sys, text, max_tokens=500)
    return kind == "sensitive"


def find_sensitive_items(tw_list: list) -> list:
    """遞迴二分找出所有會觸發內容審查的新聞（回傳被判定敏感的項目）。"""
    if not tw_list:
        return []
    if not probe_sensitive(tw_list):
        return []
    if len(tw_list) == 1:
        return list(tw_list)
    mid = len(tw_list) // 2
    return find_sensitive_items(tw_list[:mid]) + find_sensitive_items(tw_list[mid:])


def llm_analyze(market_block: str, us_close_block: str, futures_block: str,
                cnqc_news: list, tw_news: list, market_closed_note: str = "",
                now_str: str = "", session_desc: str = "",
                session_state: str = "", tsmc_gt: str = "") -> str:
    """
    根據美股昨夜收盤 + 期貨 + 國際市場數據，推理對台灣的影響。
    同時參考 CNBC 新聞解釋美股漲跌原因、與台灣本地新聞。

    若 MiniMax 內容審查（HTTP 422）拒絕整包 prompt，會自動找出並移除
    被判定的敏感新聞後重試，確保其餘新聞仍能完成分析。

    market_closed_note 非空時代表今日台股休市，會提示 LLM 不得給出開盤操作建議。
    now_str / session_desc / session_state 用來修正「時態」——
    2026/10/29 實測：報告在 14:47 生成，LLM 卻把今天盤中的新聞寫成「昨日盤中」，
    根因是 prompt 裡完全沒有「現在幾點、今天是幾號」。
    tsmc_gt 是官方收盤 ground truth，避免 LLM 把兩則新聞的數字拼在一起。
    """
    # 格式化新聞
    cnqc_text = "\n".join([
        f"{i}. {it['title']}" for i, it in enumerate(cnqc_news[:8], 1)
    ]) if cnqc_news else "（無）"

    system_prompt = """你是一個專業的台灣金融市場分析師。
根據以下市場數據與新聞，推理對台灣股市的影響方向。

任務：
1. 根據【美股昨夜收盤】與【CNBC 新聞】，解釋美股漲跌的主要驅動因素（財報、經濟數據、Fed動態、地緣事件等）
2. 根據【美股期貨當前】與【國際市場數據】，判斷台指期夜盤的方向與合理位置
3. 推斷台積電（2330）及相關供應鏈的可能走勢
4. 找出當天台灣最重要的事件（地震、政策的影響）

輸出格式（用正體中文）：
【美股昨夜驅動因素】
（3-5句，說明昨夜美股漲跌的核心原因，引用相關新聞佐證）

【對台灣的影響】
（3-5句，說明台股今日可能的开盘方向、重點觀察族群、操作建議方向）

【重點新聞解析】
（從台灣新聞中找出2-3則對台股影響最大的事件，每則用以下格式：
【重點新聞 A】事件名稱
• 事件：簡短描述
• 邏輯：為何影響台股（1-2句）
✅ 看多：受惠個股（盡量附個股代號與名稱）
❌ 看空：受害個股或族群（盡量附個股代號與名稱）

若當天沒有重大事件可分析，輸出「（今日無重大特殊事件）」即可。）

重要：請直接輸出分析內容，不要包含任何思考過程、解題步驟、說明、備註或開場白。

重要：請直接輸出分析內容，不要包含任何思考過程、解題步驟、說明、備註或開場白。絕對不要先寫英文分析再翻譯，也絕對不要輸出如"Let me analyze..."、"Key drivers..."、"Analysis:"等英文句子。"""

    closed_rule = ""
    if market_closed_note:
        closed_rule = f"""

⚠️ 重要：今日台股休市（{market_closed_note}），市場不開盤。
【對台灣的影響】段落必須明確說明「今日休市、沒有開盤」，並把觀察重點放在
「下一個交易日（復盤日）該注意什麼」，絕對不可以寫成今日開盤、不可給出
「今日搶進／今日可布局」之類的當日進場建議。"""

    # ── 時態規則：依目前時段決定【對台灣的影響】要怎麼寫 ──
    session_rule = ""
    if session_state == "pre_open":
        session_rule = """
【對台灣的影響】寫成「今日即將開盤」的預期：開盤方向、可能位置、該留意的族群與操作建議。"""
    elif session_state == "intraday":
        session_rule = """
【對台灣的影響】寫成「今日盤中」的現況：目前盤勢、盤中發生什麼、尾盤與明日該注意什麼。"""
    elif session_state == "closed":
        session_rule = """
【對台灣的影響】寫成「今日已收盤」的結果：今日收盤表現如何、盤後觀察重點、明日（下一個交易日）該注意什麼。
絕對不可以寫「今日開盤方向」「預估開高／開低」「今日可布局」——今天已經收盤了。"""

    # ── 數字規則：禁止跨新聞拼接數字 ──
    number_rules = """
【數字引用規則】（極重要）
1. 每個數字（漲跌元數、指數點數、目標價）必須來自「同一則新聞」的標題或描述，
   絕對不可以把兩則不同新聞的數字串接成一句話。
   錯例：「台積電下跌35元至25元」（35 來自新聞 A、25 來自新聞 B，是不同時點的快照）
   正例：分開寫「台積電大跌35元」「台積電跌25元」，或只寫脈絡完整的那一個數字。
2. 官方收盤資料優先於新聞標題。新聞標題常常只是盤中某個時點的快照，不代表收盤。
3. 資料標示「解析失敗」「無資料」「資料不可用」時，絕對不可自己編造該項數字，
   應直接說明該資料取得失敗。"""

    system_prompt = system_prompt + closed_rule + session_rule + number_rules

    def build_user_prompt(tw_list: list) -> str:
        tw_text = "\n".join([
            f"{i}. 【{it['ago']}】{it['title']}" for i, it in enumerate(tw_list[:12], 1)
        ]) if tw_list else "（無）"

        time_block = ""
        if now_str:
            time_block = f"""【時效資訊】（系統提供，必須遵守，絕不可自行猜測）
• 現在時間：{now_str}（台北時間）
• 交易狀態：{session_desc}
• 新聞標題後方的「N分鐘前 / N小時前 / N天前」是相對於「現在時間」計算的。
  → 「2小時前」= 從 {now_str} 往回推 2 小時，幾乎都是「今天」的事，絕不是「昨天」。
• 提到任何行情數字時，必須寫明是「今日盤中」還是「昨日（日期）」，
  不得把今天發生的事寫成「昨日」。"""
        else:
            time_block = "【時效資訊】（系統未提供時間，請避免使用昨日／今日等時態用語）"

        gt_block = ""
        if tsmc_gt:
            gt_block = f"""
【官方收盤資料（TWSE 官方 CSV，權威）】
• {tsmc_gt}
• 引用時必須標明日期；新聞標題可能是盤中快照，兩者不一致時以官方收盤為準。"""

        return f"""以下是各項市場數據：

{us_close_block}

{futures_block}

{market_block}

{time_block}

{gt_block}

以下是 CNBC 美股新聞（可解釋昨夜美股漲跌原因）：
{cnqc_text}

以下是台灣當日重要新聞：
{tw_text}
"""

    tw_candidates = list(tw_news[:12])
    dropped = []
    last_err = None

    for attempt in range(4):
        ok, raw, kind, msg = call_llm(system_prompt, build_user_prompt(tw_candidates))

        if ok:
            first_header = re.search(r"【[^】]+】", raw)
            if first_header:
                raw = raw[first_header.start():]
            if dropped:
                print(f"   ⚠️ 內容審查：已移除 {len(dropped)} 則敏感新聞後重試成功")
                for d in dropped:
                    print(f"      - {d[:60]}")
            return raw.strip()

        last_err = f"{kind}: {msg}"

        # LLM 只回傳思考過程 → 加大 max_tokens 重試一次
        if kind == "empty":
            ok2, raw2, kind2, msg2 = call_llm(
                system_prompt, build_user_prompt(tw_candidates), max_tokens=20000)
            if ok2:
                first_header = re.search(r"【[^】]+】", raw2)
                if first_header:
                    raw2 = raw2[first_header.start():]
                return raw2.strip()
            last_err = f"{kind2}: {msg2}"
            kind = kind2

        # 內容審查 → 精確找出敏感新聞並移除後重試
        if kind == "sensitive":
            bad = find_sensitive_items(tw_candidates)
            if bad:
                dropped.extend(it["title"] for it in bad)
                tw_candidates = [it for it in tw_candidates if it not in bad]
                continue
            # 找不到單一觸發項 → 全部移除台灣新聞，只用市場數據分析
            if tw_candidates:
                dropped.extend(it["title"] for it in tw_candidates)
                tw_candidates = []
                continue
            break

        break

    if last_err and last_err.startswith("sensitive"):
        return (f"⚠️ LLM 分析失敗：MiniMax 內容審查（HTTP 422）持續拒絕，"
                f"已移除 {len(dropped)} 則新聞仍無法分析（可稍後重跑）。")
    return f"⚠️ LLM 分析失敗：{last_err}"

def translate_cnbc_news(news: list[dict]) -> str:
    """將 CNBC 新聞標題翻譯成中文，適用於 Discord"""
    if not news:
        return ""
    titles = "\n".join([f"{i}. {it['title']}" for i, it in enumerate(news[:8], 1)])
    ok, raw, kind, msg = call_llm(
        "你是一個財經翻譯專家。請將以下 CNBC 新聞標題翻譯成正體中文，只需要翻譯標題，不需要改寫或解釋。保持8個標題的格式，每行前保留編號。",
        titles, max_tokens=4000)
    if ok:
        return raw
    return f"（翻譯失敗：{kind} {msg}）"

# ── Discord 推播 ─────────────────────────────────────
def send_discord(text: str) -> bool:
    chunks = []
    while len(text) > 1900:
        chunks.append(text[:1900])
        text = text[1900:]
    chunks.append(text)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }

    for chunk in chunks:
        payload = json.dumps({"content": chunk}).encode()
        req = urllib.request.Request(DISCORD_WEBHOOK, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 204:
                    print(f"   ⚠️ Discord 響應: {resp.status}")
        except Exception as e:
            print(f"   ❌ Discord 發送失敗：{e}")
            return False
    return True

# ── 主程式 ──────────────────────────────────────────
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "local"

    # 1. 國際市場數據（台指期、日經、韓股）
    print("🔍 抓取國際市場數據...")
    market = get_market_data()
    market_block = fmt_market_block(market)
    print(f"\n{market_block}\n")

    # 2. 美股昨夜收盤（S&P500、Nasdaq、VIX）
    print("🔍 抓取美股昨夜收盤...")
    us_closes = get_us_closes()
    for k, d in us_closes.items():
        val = f"{d['close']} ({d['pct']:+.2f}%)" if isinstance(d.get("close"), (int,float)) else d["close"]
        print(f"   • {d['label']}: {val}")

    # 3. CNBC 美股新聞
    print("\n🔍 抓取 CNBC RSS...")
    try:
        cnbc_data = fetch_rss(RSS_URL_CNBC)
        cnqc_news = parse_rss(cnbc_data)
        # 只取昨夜到今天的美股相關新聞
        cnqc_filtered = [it for it in cnqc_news
                          if any(kw in it["title"].lower()
                                 for kw in ["stock","market","fed","jobs","inflation","earn","chart","s&p","nasdaq"," Dow"])]
        print(f"   美股相關 {len(cnqc_filtered)} 篇，共 {len(cnqc_news)} 篇")
    except Exception as e:
        print(f"   ❌ CNBC RSS 失敗：{e}")
        cnqc_filtered = []

    # 4. 美股期貨
    print("\n🔍 抓取美股期貨...")
    us_futures = get_us_futures()
    for k, d in us_futures.items():
        val = f"{d['close']} ({d['pct']:+.2f}%)" if isinstance(d.get("close"), (int,float)) else d["close"]
        print(f"   • {d['label']}: {val}")

    # 5. 台灣新聞
    print("\n🔍 抓取台灣新聞...")
    try:
        tw_data  = fetch_rss(RSS_URL_TW)
        tw_items = parse_rss(tw_data)
        tw_relevant = [it for it in tw_items if is_relevant_tw(it["title"], it["desc"])]
        tw_news = (tw_relevant[:15] if tw_relevant else tw_items[:10])
        print(f"   總共 {len(tw_items)} 則，財經相關 {len(tw_relevant)} 則")
    except Exception as e:
        print(f"   ❌ 台灣 RSS 失敗：{e}")
        tw_news = []

    # 6. LLM 分析
    print("\n🤖 正在呼叫 MiniMax-M3 分析...")
    futures_block = fmt_us_futures_block(us_futures)
    us_close_block_discord = fmt_us_close_block_discord(us_closes)
    us_close_block_llm     = fmt_us_close_block(us_closes, cnqc_filtered)

    now_dt  = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M")

    # 休市日：通知 LLM 不得給出「今日開盤」的操作建議
    today_str = now_dt.strftime("%Y-%m-%d")
    market_closed_note = ""
    if not is_trading_day(today_str):
        market_closed_note = holiday_reason(today_str)
        print(f"⏭️  今日休市（{market_closed_note}），報告將標註休市並改以復盤日觀察重點呈現。")

    # 時段狀態 + 官方收盤 ground truth（修時態錯誤與跨新聞數字誤植）
    session_state, session_desc = market_session_state(now_dt)
    tsmc_gt = get_tsmc_ground_truth()
    print(f"   🕘 時段狀態：{session_desc}")
    print(f"   📐 官方收盤：{tsmc_gt}")

    # LLM 要拿到含 CNBC 新聞的版本（因果鏈來源）；Discord 版本不含 CNBC。
    analysis = llm_analyze(market_block, us_close_block_llm, futures_block,
                           cnqc_filtered, tw_news, market_closed_note,
                           now_str=now_str, session_desc=session_desc,
                           session_state=session_state, tsmc_gt=tsmc_gt)

    # ── 組 Discord 報告 ────────────────────────────────
    md_lines = []
    md_lines.append(f"## 📊 金融事件日報  `({now_str})`")
    md_lines.append("")
    if market_closed_note:
        md_lines.append(f"> 🚫 **今日台股休市（{market_closed_note}）**，市場不開盤。")
        md_lines.append("> 下方【對台灣的影響】以「下一個交易日」為觀察重點，不含當日進場建議。")
        md_lines.append("")
    elif session_state != "pre_open":
        md_lines.append(f"> 🕘 {session_desc}。")
        md_lines.append("")
    md_lines.append(market_block)
    md_lines.append("")
    md_lines.append(us_close_block_discord)
    md_lines.append("")
    md_lines.append(futures_block)
    md_lines.append("")
    # 分析內容由 LLM 產生，含三個段落：
    # 【美股昨夜驅動因素】/【對台灣的影響】/【重點新聞解析】
    # 重新整理標題與段落，避免重複標題與殘留英文思考。
    analysis = strip_think(analysis)
    analysis = strip_english_lines(analysis)
    # 修補跨新聞拼接的數字矛盾（例：「下跌35元至25元」）
    analysis, contradictions = sanitize_contradictions(analysis)
    if contradictions:
        print(f"   ⚠️ 已修正跨新聞拼接的數字矛盾：{'；'.join(contradictions)}")

    sec = split_sections(analysis)

    # LLM 整段失敗時（回傳 ⚠️ 開頭的錯誤訊息）直接顯示錯誤，
    # 不要靜默顯示「（無）」讓人以為是「分析不出內容」。
    llm_failed = analysis.startswith("⚠️")

    md_lines.append("【美股驅動因素】")
    if llm_failed:
        md_lines.append(analysis)
    else:
        md_lines.append(sec.get("美股昨夜驅動因素", "（無）"))
    md_lines.append("")
    if not llm_failed:
        md_lines.append("【對台灣的影響】")
        md_lines.append(sec.get("對台灣的影響", "（無）"))
        md_lines.append("")
        if sec.get("重點新聞解析"):
            md_lines.append("【重點新聞解析】")
            md_lines.append(sec["重點新聞解析"])
            md_lines.append("")
    md_lines.append("【當日重要新聞】")
    for i, it in enumerate(tw_news[:15], 1):
        md_lines.append(f"{i}. {it['title']}（{it['ago']}）")

    md_report = "\n".join(md_lines)

    print("\n" + "=" * 60)
    print(md_report)

    # 存檔
    out_path = "/tmp/finance_daily_report.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"\n✅ 報告已存：{out_path}")

    # Discord
    if mode == "discord":
        print("\n📤 發送到 Discord...")
        ok = send_discord(md_report)
        print("✅ Discord 發送成功" if ok else "❌ Discord 發送失敗")

if __name__ == "__main__":
    main()
