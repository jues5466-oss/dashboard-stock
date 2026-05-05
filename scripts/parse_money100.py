#!/usr/bin/env python3
"""
錢線百分百 - VTT 解析腳本
用途：讀取 VTT 字幕檔，產出結構化 CSV + Markdown 重點整理
模式：
  1. OPENAI_API_KEY 設定 → AI 解析（GPT-4o-mini）
  2. 無 API Key → 關鍵字比對解析（備援模式）
"""
import sys
import os
import re
import csv
import json
import glob
import requests
from datetime import datetime

# ── 設定 ──────────────────────────────────────────────────────
BASE_DIR    = '/Volumes/AI_Drive/StockData_v2/data/money100'
SUB_DIR     = f'{BASE_DIR}/subs'
SUMMARY_DIR = f'{BASE_DIR}/episode_summary'
CSV_PATH    = f'{BASE_DIR}/mentioned_stocks.csv'

DISCORD_WEBHOOK = 'https://discord.com/api/webhooks/1500875786759180419/mDbDN_Itv3WUxrgDNLlg_g9BbuFuvEui3dIjLMwXLF43-sZYApY7WLrYSIaNsB6y-KBc'

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', None)
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', None)
MINIMAX_API_KEY=os.getenv('MINIMAX_API_KEY', '')
MINIMAX_BASE_URL = 'https://api.minimax.io/v1'

# ── 已知股票資料庫 ────────────────────────────────────────────
KNOWN_STOCKS = {
    '2456': '聯發科', '3711': '日月光投控', '2330': '台積電',
    '2317': '鴻海', '2303': '聯電', '2474': '可成',
    '3034': '聯詠', '2376': '技嘉', '2368': '金像電',
    '2377': '微星', '2492': '華新科', '3006': '晶華',
    '3576': '聯合再生', '3016': '嘉聯益', '4952': '凌通',
    '6176': '瑞儀', '6415': '矽力-KY',
    '2458': '義隆', '2395': '研華', '1536': '和大',
    '1590': '京元電子', '6238': '緯穎', '3665': '天虹',
    '1704': '友達', '2409': '友達', '2344': '華邦電',
    '4763': '南茂', '3014': '新唐', '2342': '茂迪',
    '2610': '華航', '5871': '中租-KY', '5880': '合庫金',
    '2633': '長榮', '2891': '中信金', '2882': '國泰金',
    '3486': '定穎投控', '6271': '大同',
    '2401': '凌陽', '8064': '勝利科技',
    '6488': 'GIS-KY', '1316': '新日光', '2301': '光寶科',
    '6706': '惠特', '3545': '晶彩科', '5457': '悅城',
    '3443': '創意', '3661': '世芯-KY', '3013': '安集',
    '2345': '智邦', '3532': '台勝科', '3563': '散熱',
    '2383': '台光電', '6213': '聯茂', '4938': '和碩',
    '2327': '國巨', '2451': '創見', '3535': '晶彩科',
    '2340': '光磊', '2491': '首利', '2484': '希華',
    '6257': '矽格', '3035': '智原', '3229': '新日興',
    '3055': '昇印', '3662': '長聖', '3292': '笙科',
    '6202': '盛群', '3536': '新至陞', '3042': '晶技',
    '6196': '帆宣', '3045': '五福', '6180': '橘子',
    '6182': '簡訊', '3164': '岳鼎', '6183': '朋程',
    '6186': 'F-虹堡', '6191': '精成科', '3221': '大甲',
    '3653': '健策', '6177': '大江', '6285': '君耀-KY',
    '2486': '美律', '3010': '華立', '6165': '泰博',
    '3019': '悠克', '3047': '聚積', '6289': '安迅',
    '2497': '怡利電', '2493': '升科大',
    '4536': '拓凱', '1805': '博大', '2367': '系統電',
    '2498': '宏達電', '2499': '益通', '2542': '華固',
    '2603': '長榮', '2605': '萬海', '2609': '陽明',
    '2617': '台聚', '2886': '兆豐金', '2890': '富邦金',
    '3008': '大立光', '3036': '文曄', '3041': '合勤',
    '3105': '穩懋', '3189': '景碩', '3413': '京鼎',
    '3486': '定穎投控', '3504': '友達', '3607': '谷崧',
    '3661': '世芯-KY', '3714': '富采', '3722': '川湖',
    '4943': '康聯', '4952': '凌通', '4971': '晶心科',
    '4973': '創惟', '4979': '華星光', '4987': '訊芯-KY',
    '5299': '杰力', '5347': '世界', '5351': '穎崴',
    '5371': '中光電', '5388': '中磊', '5471': '松翰',
    '5483': '中美晶', '5536': '聖暉', '5706': '鳳凰',
    '5871': '中租', '6112': '邁達', '6146': '耕興',
    '6223': '旺矽', '6257': '矽格', '6277': '宏正',
    '6415': '矽力-KY', '6426': '鼎翰', '6441': 'F-永冠',
    '6477': '安集', '6509': '聚鼎', '6579': '研晶',
    '6616': '達能', '6625': '光洋科', '6640': '華景',
    '6706': '惠特', '6727': '泰博', '6770': '力士',
    '8038': '長科', '8046': '南電', '8070': '長華',
    '8081': '致新', '8105': '撼訊', '8131': '福懋科',
    '8150': '信邦', '8163': '達方', '8205': '昆盈',
    '8234': '新保', '8410': '永道', '8411': '福裕',
    '8420': '明安', '8436': '大江', '8454': '富邦媒',
    '8482': '商之器', '8495': '邑錡', '8996': '大拓',
    '9904': '寶成', '9910': '豐泰', '9911': '美利',
    '9917': '中保', '9925': '新海', '9955': '冠星',
    # ETF
    '0050': '元大台灣50', '0056': '元大高股息',
    '00878': '國泰永續高股息', '00919': '群益台灣精選高息',
    '00980': '野村臺灣優選', '00980A': '野村臺灣優選',
}

# ── 分類關鍵字 ────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    'AI ASIC': ['ASIC', 'AI ASIC', '自研晶片', '特殊應用IC', 'AI晶片', 'TPU'],
    'CoPoS/玻璃基板': ['CoPoS', '玻璃基板', 'TGV', 'FOPLP', 'FOWLP', '面板級'],
    '記憶體': ['記憶體', 'DRAM', 'NAND', 'HBM', '模組', 'DDR5', 'DDR4'],
    '封測': ['封測', '日月光', '京元電', '力成', '南茂', '福懋科', '華泰', '華東'],
    '矽光子': ['矽光子', '光通訊', '光纖', '聯亞', '華星光', '波若威', '上詮', '光聖'],
    '主動式ETF': ['ETF', '主動式', '00980', '野村', '00919', '0056', '00878', '月月配'],
    '台積電/半導體': ['台積電', '晶圓', 'CoWoS', '先進製程', '先進封裝'],
    '散熱': ['散熱', '奇鋐', '雙鴻', '建準', '泰碩', '液冷'],
    '驅動IC': ['驅動IC', 'TDDI', 'OLED', '聯詠', '敦泰', '天鈺'],
    'PCB/CCL': ['PCB', 'CCL', 'ABF', '載板', '欣興', '南電', '景碩', '臻鼎', '金像電', '聯茂', '台光電'],
    'AI伺服器': ['GB200', 'GB300', 'Rubin', 'AI伺服器', 'AI server', 'ODM', '廣達', '緯穎', '英業達'],
    '低軌衛星': ['低軌衛星', 'Starlink', 'OneWeb'],
    '機器人': ['機器人', '人形機器人', 'AI機器人', '自動化'],
    '其他': [],
}

POSITION_KEYWORDS = {
    '創高': ['創新高', '歷史高', '噴出', '飆漲', '漲停', '帶量大漲', '歷史天價'],
    '突破': ['突破', '過高', '挑戰前高', '突破整理', '過季線', '過月線', '帶量突破'],
    '整理': ['整理', '拉回', '休息', '打底', '震盪', '季線', '月線', '橫向'],
    '落後補漲': ['落後', '補漲', '低價', '還在', '相對低', '百元內', '低估'],
    '高檔': ['高檔', '高位', '本益比高', '貴', '風險'],
}


def parse_vtt(vtt_path):
    """讀取 VTT 檔，回傳乾淨的中文字幕"""
    with open(vtt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line or '-->' in line or line in ('WEBVTT', 'Kind:', 'Language:') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        line = re.sub(r'<[^>]+>', '', line)
        if line:
            text_lines.append(line)
    return ' '.join(text_lines)


def get_snippet(text, keyword, before=400, after=200):
    """取出包含關鍵字的前後文片段"""
    idx = text.find(keyword)
    if idx == -1:
        return ''
    start = max(0, idx - before)
    end = min(len(text), idx + after)
    snippet = text[start:end]
    # 清理多餘空白
    snippet = re.sub(r' +', ' ', snippet)
    return snippet.strip()


def keyword_parse(text):
    """用關鍵字比對方式解析 VTT"""
    results = {}
    for code, name in KNOWN_STOCKS.items():
        occurrences = []
        for keyword in [name, code]:
            idx = 0
            while True:
                pos = text.find(keyword, idx)
                if pos == -1:
                    break
                snippet = get_snippet(text, keyword, before=300, after=200)
                if snippet:
                    occurrences.append(snippet)
                idx = pos + 1

        if not occurrences:
            continue

        combined = ' '.join(occurrences)

        # 分類
        category = '其他'
        for cat, kws in CATEGORY_KEYWORDS.items():
            if any(kw in combined for kw in kws):
                category = cat
                break

        # 位階
        position = '一般'
        for pos, kws in POSITION_KEYWORDS.items():
            if any(kw in combined for kw in kws):
                position = pos
                break

        # 原因
        reason = ''
        for kw in CATEGORY_KEYWORDS.get(category, []):
            if kw in combined:
                reason = kw
                break
        if not reason:
            reason = category if category != '其他' else '節目提及'

        if code not in results or len(combined) > len(results[code].get('description', '')):
            results[code] = {
                'code': code,
                'name': name,
                'reason': reason,
                'category': category,
                'position': position,
                'description': combined[:600].strip(),
            }

    return list(results.values())


def extract_with_ai(text, date_str):
    """用 GPT-4o-mini 解析"""
    if not OPENAI_API_KEY:
        return {}

    try:
        from openai import OpenAI
    except ImportError:
        return {}

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"""你是台股分析師。請從以下【錢線百分百】節目字幕中，萃取出節目討論的各大重點。

產出格式（JSON物件）：
{{
  "大盤概況": "當日大盤重點描述：指數表現、漲跌、成交量、重點權值股動向",
  "重量級話題": "當日最重要的一個主題及其關鍵數據/目標價/理由",
  "AI_ASIC供應鏈": ["個股1（代碼）- 簡評", "個股2（代碼）- 簡評", ...],
  "CoPoS玻璃基板": ["個股1（代碼）- 簡評", "個股2（代碼）- 簡評", ...],
  "矽光子": ["個股1（代碼）- 簡評", "個股2（代碼）- 簡評", ...],
  "主動式ETF": ["ETF點評重點"],
  "本週關注標的": ["標的1 - 理由", "標的2 - 理由", ...],
  "分析師觀點": {{"分析師名": "立場與觀點", ...}},
  "個股詳細": [
    {{
      "code": "代碼",
      "name": "名稱",
      "category": "分類",
      "position": "位階",
      "reason": "節目提到原因",
      "description": "節目中完整說明（盡量完整保留分析師觀點，100-300字）"
    }}
  ]
}}

【字幕內容】：
{text[:15000]}
"""
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.3, max_tokens=4000
        )
        result = resp.choices[0].message.content
        result = re.sub(r'^```json\s*', '', result)
        result = re.sub(r'\s*```$', '', result)
        data = json.loads(result)
        print(f"  → AI 解析完成")
        return data
    except Exception as e:
        print(f"  ⚠️ AI 解析失敗: {e}")
        return {}


def extract_gemini_summary(text, date_str, stocks):
    """用 Gemini 生成結構化摘要（股票已由關鍵字系統抓取）"""
    try:
        import google.generativeai as genai
    except ImportError:
        print("  ⚠️ Gemini SDK 未安裝")
        return {}

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-flash-latest')
    except Exception as e:
        print(f"  ⚠️ Gemini 初始化失敗: {e}")
        return {}

    # 股票摘要（供 AI 参考）
    stock_brief = '\n'.join([
        f"- {s['code']} {s['name']}: {s['reason'][:80]}"
        for s in stocks
    ]) if stocks else "（無）"

    # Gemini 切片摘要（配額用完則跳過）
    MAX_CHARS = 6000
    chunks = [text[i:i+MAX_CHARS] for i in range(0, len(text), MAX_CHARS)]
    all_sections = {}
    QUOTA_EXCEEDED = False

    for i, chunk in enumerate(chunks):
        chunk_label = f"（第{i+1}/{len(chunks)}段）" if len(chunks) > 1 else "（完整內容）"
        try:
            prompt = f"""你是台灣股市分析師，擅長解讀電視節目內容並整理成結構化摘要。

【任務】根據以下「錢線百分百」節目字幕，生成結構化分析摘要。

【已知節目提及的股票】（由關鍵字系統抓取，供參考）：
{stock_brief}

【字幕內容 {chunk_label}】：
{chunk}

【產出格式】（請直接輸出 JSON，不要 markdown 代碼塊）：
{{
  "大盤概況": "指數表現、重點數據（150字以內）",
  "重量級話題": "當日最重要主題與關鍵數據（100字以內）",
  "AI_ASIC供應鏈": ["個股點評"],
  "先進封裝": ["個股點評"],
  "主動式ETF": ["ETF重點"],
  "本週關注標的": ["標的1 - 理由"],
  "分析師觀點": "各分析師立場摘要（100字以內）"
}}
"""
            response = model.generate_content(prompt)
            raw = response.text
            raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
            raw = re.sub(r'\s*```\s*$', '', raw)
            chunk_data = json.loads(raw)
            for k, v in chunk_data.items():
                if isinstance(v, list):
                    if k not in all_sections:
                        all_sections[k] = []
                    seen = set(all_sections[k])
                    for item in v:
                        if item not in seen:
                            all_sections[k].append(item)
                            seen.add(item)
                elif k not in all_sections:
                    all_sections[k] = v
            print(f"  → Chunk {i+1}/{len(chunks)} 完成")
        except Exception as e:
            err_str = str(e)
            if '429' in err_str or 'quota' in err_str.lower():
                print(f"  ⚠️ Gemini 配額已滿（{len(chunks)-i-1} 段跳過），將使用關鍵字摘要")
                QUOTA_EXCEEDED = True
                break
            print(f"  ⚠️ Chunk {i+1} 失敗: {e}")
            continue

    if all_sections:
        all_sections['個股詳細'] = stocks
        print(f"  → Gemini 摘要完成（{len(stocks)} 檔股票已合併）")
        return all_sections
    return {}


def summarize_episode_minimax(vtt_text, episode_label, stocks_brief):
    """用 MiniMax 為單集字幕生成章節式摘要（每集分多 chunk，各自濃縮再合併）"""
    try:
        from openai import OpenAI
    except ImportError:
        print("  ⚠️ OpenAI SDK 未安裝")
        return {}

    try:
        client = OpenAI(api_key=MINIMAX_API_KEY, base_url=MINIMAX_BASE_URL)
    except Exception as e:
        print(f"  ⚠️ MiniMax 初始化失敗: {e}")
        return {}

    # 每集 VTT 約 17000 字，分成 ~4000 字 chunk，各自濃縮成 150 字，最後合併
    MAX_CHARS = 4000
    chunks = [vtt_text[i:i+MAX_CHARS] for i in range(0, len(vtt_text), MAX_CHARS)]
    chunk_summaries = []

    for i, chunk in enumerate(chunks):
        label = f"{episode_label} 第{i+1}/{len(chunks)}段"
        try:
            prompt = f"""你是台灣股市分析師，擅長解讀電視節目口語內容。

【任務】根據以下「錢線百分百」{label}字幕，生成一段 200 字以內的章節式摘要。

【已知本集提及的股票】（供參考）：
{stocks_brief}

【{label}字幕內容】：
{chunk}

【產出格式】直接輸出以下 JSON（不要 markdown、不要思考過程、不要任何解釋）：
{{
  "章節標題": "這段內容的章節主題（10字以內）",
  "摘要": "200字以內的本段節目重點摘要（請條列式，1-3句話覆蓋大盤、話題、股票）"
}}"""
            resp = client.chat.completions.create(
                model='MiniMax-M2.5',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.3,
                max_tokens=400,
                response_format={'type': 'json_object'}
            )
            raw = resp.choices[0].message.content.strip()
            # 去掉 MiniMax CoT 思考區塊
            raw = re.sub(r'^.+?</think>\s*', '', raw, flags=re.DOTALL)
            # 去掉 markdown 包裝
            raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
            raw = re.sub(r'\s*```\s*$', '', raw)
            # 找第一個 { 當 JSON 起點，取到最後一個 }
            json_start = raw.find('{')
            json_end = raw.rfind('}')
            if json_start >= 0 and json_end > json_start:
                raw = raw[json_start:json_end+1]
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # 最後一道防線：用 regex 強行抽出有效欄位
                ch = re.search(r'["\u201c]\u7ae0\u7bc0\u6a19\u984c["\u201d]\s*:\s*["\u201c]([^"\u201d]+)["\u201d]', raw)
                sm = re.search(r'["\u201c]\u6458\u8981["\u201d]\s*:\s*["\u201c]([^"\u201d]{10,})["\u201d]', raw)
                if ch and sm:
                    data = {'\u7ae0\u7bc0\u6a19\u984c': ch.group(1), '\u6458\u8981': sm.group(1)}
                else:
                    raise
            chapter = data.get('章節標題', f'第{i+1}段')
            summary = data.get('摘要', '')
            if summary and len(summary) > 20:
                chunk_summaries.append(f"【{chapter}】{summary}")
                print(f"    {label}: {chapter}")
        except Exception as e:
            print(f"  ⚠️ {label} 失敗: {e}")
            continue

    if chunk_summaries:
        return {
            '章節摘要': chunk_summaries,
            '完整文字': '\n\n'.join(chunk_summaries)
        }
    return {}


def merge_episode_summaries(episode_results):
    """將三集各自摘要合併成一個結構化 dict"""
    all_chapters = []
    for ep_label, result in episode_results.items():
        if result and result.get('章節摘要'):
            all_chapters.extend([
                f"**{ep_label}**",
                *[f"  {c}" for c in result['章節摘要']]
            ])
    if all_chapters:
        return {'各集章節': all_chapters}
    return {}


def build_discord_md(date_str, data, stocks):
    """產出類似第一次那種詳細整理的 Discord Markdown"""
    date_display = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"

    lines = [f"## 📺 錢線百分百 {date_display} 重點整理\n"]

    # 一、大盤概況
    if data.get('大盤概況'):
        lines.append(f"**一、大盤概況**\n- {data['大盤概況']}\n")

    # 二、重量級話題
    if data.get('重量級話題'):
        lines.append(f"**二、重量級話題**\n- {data['重量級話題']}\n")

    # 三、AI ASIC
    if data.get('AI_ASIC供應鏈'):
        lines.append("**三、AI ASIC 供應鏈**\n")
        for item in data['AI_ASIC供應鏈']:
            lines.append(f"- {item}")
        lines.append("")

    # 四、CoPoS/玻璃基板
    if data.get('CoPoS玻璃基板'):
        lines.append("**四、先進封裝（CoPoS 玻璃基板）**\n")
        for item in data['CoPoS玻璃基板']:
            lines.append(f"- {item}")
        lines.append("")

    # 五、矽光子
    if data.get('矽光子'):
        lines.append("**五、矽光子**\n")
        for item in data['矽光子']:
            lines.append(f"- {item}")
        lines.append("")

    # 六、主動式ETF
    if data.get('主動式ETF'):
        lines.append("**六、主動式 ETF**\n")
        for item in data['主動式ETF']:
            lines.append(f"- {item}")
        lines.append("")

    # 七、本週關注標的
    if data.get('本週關注標的'):
        lines.append("**七、本週可留意標的**\n")
        for item in data['本週關注標的']:
            lines.append(f"- {item}")
        lines.append("")

    # 八、分析師觀點
    analyst_views = data.get('分析師觀點', {})
    if isinstance(analyst_views, str):
        lines.append("**八、四位分析師觀點**\n")
        lines.append(f"- {analyst_views}")
    elif analyst_views:
        lines.append("**八、四位分析師觀點**\n")
        for analyst, view in analyst_views.items():
            lines.append(f"- **{analyst}**：{view}")
        lines.append("")

    # 九、個股詳細（ optionally, if stocks list is rich)
    if stocks:
        # 只取前8檔最重要的
        top = stocks[:8]
        lines.append("---\n\n**📋 個股重點**\n\n")
        for s in top:
            lines.append(f"### {s['name']}（{s['code']}）\n")
            lines.append(f"**原因：** {s['reason']} | **位階：** `{s['position']}`\n")
            lines.append(f"{s.get('description', '')[:300]}\n\n")

    return '\n'.join(lines)


def build_summary_markdown(date_str, data, stocks):
    """產出完整 Markdown"""
    date_display = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"

    lines = [f"# 📺 錢線百分百 {date_display} 重點整理\n"]

    if data:
        sections = [
            ('大盤概況', '一、大盤概況'),
            ('重量級話題', '二、重量級話題（當日最重要主題）'),
            ('AI_ASIC供應鏈', '三、AI ASIC 供應鏈'),
            ('CoPoS玻璃基板', '四、先進封裝（CoPoS 玻璃基板）'),
            ('矽光子', '五、矽光子'),
            ('主動式ETF', '六、主動式 ETF'),
            ('本週關注標的', '七、本週可留意標的'),
            ('分析師觀點', '八、四位分析師觀點'),
        ]
        for key, title in sections:
            if data.get(key):
                if isinstance(data[key], list):
                    lines.append(f"## {title}\n")
                    for item in data[key]:
                        lines.append(f"- {item}")
                    lines.append("")
                elif isinstance(data[key], dict):
                    lines.append(f"## {title}\n")
                    for analyst, view in data[key].items():
                        lines.append(f"- **{analyst}**：{view}")
                    lines.append("")
                else:
                    lines.append(f"## {title}\n{data[key]}\n")

    if stocks:
        lines.append("---\n\n## 📋 個股重點（完整列表）\n\n")
        for s in stocks:
            lines.append(f"### {s['name']}（{s['code']}）\n")
            lines.append(f"**原因：** {s['reason']}  |  **分類：** `{s['category']}`  |  **位階：** `{s['position']}`\n")
            lines.append(f"**詳述：** {s.get('description', '')}\n\n")

    return '\n'.join(lines)


def save_csv(stocks, date_str):
    os.makedirs(BASE_DIR, exist_ok=True)
    existing = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('date') != date_str:
                    existing.append(row)

    fieldnames = ['date', 'code', 'name', 'reason', 'category', 'position', 'description']
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)
        for s in stocks:
            writer.writerow({
                'date': date_str, 'code': s.get('code', ''),
                'name': s.get('name', ''), 'reason': s.get('reason', ''),
                'category': s.get('category', '其他'), 'position': s.get('position', '一般'),
                'description': s.get('description', '')
            })
    print(f"  → CSV: {CSV_PATH}")


def save_markdown(content, date_str):
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    path = f'{SUMMARY_DIR}/{date_str}.md'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  → MD: {path}")
    return path


def send_discord_md(title, md_content, webhook_url):
    """分段發送 Markdown 到 Discord（每則 1900 字）"""
    # 先發標題
    payload = {'content': f"**{title}**"}
    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except:
        pass

    # 分段發內容
    chunks = []
    current = ''
    for line in md_content.split('\n'):
        if len(current) + len(line) + 1 > 1900:
            if current:
                chunks.append(current)
            current = line
        else:
            current += ('\n' + line if current else line)

    if current:
        chunks.append(current)

    for chunk in chunks:
        payload = {'content': chunk}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code not in (200, 204):
                print(f"  ⚠️ Discord 第{i+1}段發送失敗: {resp.status_code}")
        except Exception as e:
            print(f"  ⚠️ Discord 發送失敗: {e}")
        import time; time.sleep(0.5)


def send_discord_simple(title, content, webhook_url):
    """發送純文字到 Discord"""
    MAX_LEN = 1900
    if len(content) > MAX_LEN:
        content = content[:MAX_LEN] + '\n...(內容過長，已截斷)'
    payload = {'content': f"**{title}**\n\n{content}"}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            print(f"  → Discord 通知已發送")
            return True
        print(f"  ⚠️ Discord 失敗: {resp.status_code}")
    except Exception as e:
        print(f"  ⚠️ Discord 失敗: {e}")
    return False


def main():
    date_str = sys.argv[1] if len(sys.argv) >= 2 else datetime.now().strftime('%Y%m%d')

    print(f"\n📺 錢線百分百 解析腳本")
    print(f"   日期: {date_str}")
    print(f"   時間: {datetime.now().strftime('%H:%M:%S')}")

    # 找字幕檔（當天所有集）
    vtt_files = sorted(glob.glob(f'{SUB_DIR}/{date_str}.*.vtt'))
    if not vtt_files:
        print(f"\n❌ 找不到字幕檔，請先執行 fetch_money100.py {date_str}")
        sys.exit(1)

    print(f"\n📄 字幕檔 ({len(vtt_files)} 集):")
    for vf in vtt_files:
        print(f"   {os.path.basename(vf)}")

    # ── 三集分開處理 ──────────────────────────────────────────
    episode_results = {}   # ep_label -> {章節摘要, 完整文字}
    all_stocks = []        # 彙總所有集的股票
    episode_stocks_map = {} # ep_label -> [stocks from that episode]

    for vf in vtt_files:
        ep_label = os.path.basename(vf).replace(f'{date_str}.', '').replace('.zh-Hant.vtt', '')
        print(f"\n{'='*50}")
        print(f"📡 處理：{ep_label}")

        # 讀取單集字幕
        vtt_text = parse_vtt(vf)
        if len(vtt_text) < 100:
            print(f"  ⚠️ 字幕過短，略過")
            continue

        # 單集關鍵字解析（股票）
        print(f"  🔑 關鍵字解析...")
        stocks = keyword_parse(vtt_text)
        print(f"     → {len(stocks)} 檔股票")
        episode_stocks_map[ep_label] = stocks
        all_stocks.extend(stocks)

        # 單集關鍵字摘要（無 AI）
        print(f"  📝 關鍵字摘要...")
        summary = build_structured_summary(vtt_text, stocks)
        def _fmt(v):
            if isinstance(v, str):
                return v[:80]
            if isinstance(v, dict):
                return ', '.join([f"{a}:{s[:40]}" for a, s in list(v.items())[:3]])
            if isinstance(v, list):
                return ', '.join(v[:3])
            return str(v)[:80]

        episode_results[ep_label] = {
            '章節摘要': [f"{k}: {_fmt(v)}" for k, v in summary.items() if v],
            '完整文字': '\n'.join([f"{k}: {_fmt(v)}" for k, v in summary.items() if v])
        }
        print(f"     → {ep_label} 完成")

    if not episode_results:
        print("❌ 所有集摘要均失敗，結束")
        sys.exit(1)

    # ── 合併所有集股票（去重，保留最長 description）───────
    print(f"\n🔄 合併股票、去重...")
    stock_map = {}
    for s in all_stocks:
        code = s.get('code')
        if code not in stock_map or len(s.get('description', '')) > len(stock_map[code].get('description', '')):
            stock_map[code] = s
    merged_stocks = list(stock_map.values())
    print(f"  → 去重後共 {len(merged_stocks)} 檔股票")

    # ── 產出 Markdown ────────────────────────────────────────
    print(f"\n📝 生成完整 Markdown...")
    full_md = build_combined_markdown(date_str, episode_results, merged_stocks)
    md_path = save_markdown(full_md, date_str)

    # ── Discord 通知 ─────────────────────────────────────────
    print(f"\n📤 發送 Discord 通知...")
    discord_md = build_combined_discord_md(date_str, episode_results, merged_stocks)
    try:
        send_discord_md(f"📺 錢線百分百 {date_str} 重點整理", discord_md, DISCORD_WEBHOOK)
        print(f"  → Discord 通知已發送")
    except Exception as e:
        print(f"  ⚠️ Discord 發送失敗: {e}")

    # ── CSV ──────────────────────────────────────────────────
    if merged_stocks:
        save_csv(merged_stocks, date_str)
    else:
        print("  → 無股票資料，略過 CSV")

    print(f"\n✅ 完成！")


def build_combined_markdown(date_str, episode_results, stocks):
    """產出合併後的完整 Markdown（三集章節 + 股票）"""
    date_display = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
    lines = [f"# 📺 錢線百分百 {date_display} 重點整理\n"]

    # 各集章節摘要
    lines.append("## 📡 各集章節摘要\n")
    for ep_label, result in episode_results.items():
        if result and result.get('章節摘要'):
            lines.append(f"### ▶ {ep_label}\n")
            for ch in result['章節摘要']:
                lines.append(f"- {ch}")
            lines.append("")

    # 股票
    if stocks:
        lines.append("---\n\n## 📋 個股重點（完整列表）\n")
        for s in stocks:
            lines.append(f"### {s['name']}（{s['code']}）\n")
            lines.append(f"**原因：** {s['reason']}  |  **分類：** `{s['category']}`  |  **位階：** `{s['position']}`\n")
            lines.append(f"**詳述：** {s.get('description', '')}\n\n")

    return '\n'.join(lines)


def build_combined_discord_md(date_str, episode_results, stocks):
    """產出 Discord 用的 Markdown（三集各自章節 + 股票精選）"""
    date_display = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
    lines = [f"## 📺 錢線百分百 {date_display} 重點整理\n"]

    # 各集章節
    for ep_label, result in episode_results.items():
        if result and result.get('章節摘要'):
            lines.append(f"**▶ {ep_label}**\n")
            for ch in result['章節摘要']:
                lines.append(f"  {ch}")
            lines.append("")

    # 股票精選（前8檔）
    if stocks:
        lines.append("---\n\n**📋 個股重點**\n\n")
        for s in stocks[:8]:
            lines.append(f"### {s['name']}（{s['code']}）\n")
            lines.append(f"**原因：** {s['reason']} | **位階：** `{s['position']}`\n")
            lines.append(f"{s.get('description', '')[:250]}\n\n")

    return '\n'.join(lines)


def build_structured_summary(text, stocks):
    """沒有 AI 時，用關鍵字整理出結構化摘要（章節式）"""
    data = {}

    # 大盤概況 — 找指數、漲點、權值股
    index_kw = ['創新高', '大漲', '漲點', '站上', '指數', '收盤', '漲停', '外资', '買超']
    snippets = []
    for kw in index_kw:
        s = get_snippet(text, kw, before=200, after=100)
        if s:
            snippets.append(s)
    if snippets:
        # 取最長的一段當大盤概況
        best = max(snippets, key=len)
        # 清理成一句話
        best = re.sub(r'^[^，節]*節目[^，]*，', '', best)
        data['大盤概況'] = best[:300].strip()

    # 找重量級話題（最高提及次數的單一主題）
    topic_kws = ['目標價', '5000元', 'AI ASIC', '超級循環', 'CoPoS', '玻璃基板', '主動式ETF', '00980']
    topic_scores = {}
    for kw in topic_kws:
        topic_scores[kw] = text.count(kw)
    if topic_scores:
        top_topic = max(topic_scores, key=topic_scores.get)
        snippet = get_snippet(text, top_topic, before=300, after=200)
        data['重量級話題'] = f"【{top_topic}】{snippet[:250].strip()}"

    # AI ASIC 供應鏈
    asic_stocks = [s for s in stocks if s.get('category') == 'AI ASIC']
    if asic_stocks:
        data['AI_ASIC供應鏈'] = [
            f"{s['name']}（{s['code']}）- {s.get('description', '')[:80].strip()}"
            for s in asic_stocks[:6]
        ]

    # CoPoS/玻璃基板
    copoS_stocks = [s for s in stocks if s.get('category') == 'CoPoS/玻璃基板']
    if copoS_stocks:
        data['CoPoS玻璃基板'] = [
            f"{s['name']}（{s['code']}）- {s.get('description', '')[:80].strip()}"
            for s in copoS_stocks[:6]
        ]

    # 矽光子
    photon_stocks = [s for s in stocks if s.get('category') == '矽光子']
    if photon_stocks:
        data['矽光子'] = [
            f"{s['name']}（{s['code']}）- {s.get('description', '')[:80].strip()}"
            for s in photon_stocks[:5]
        ]

    # 主動式ETF
    etf_stocks = [s for s in stocks if s.get('category') == '主動式ETF']
    if etf_stocks:
        data['主動式ETF'] = [
            f"{s['name']}（{s['code']}）- {s.get('description', '')[:100].strip()}"
            for s in etf_stocks[:4]
        ]

    # 本週關注標的（整理或落後補漲位階的股票）
    watch_stocks = [s for s in stocks if s.get('position') in ('整理', '落後補漲', '突破')]
    if watch_stocks:
        data['本週關注標的'] = [
            f"{s['name']}（{s['code']}）- {s.get('reason', '')} - {s.get('position', '')}"
            for s in watch_stocks[:6]
        ]

    # 分析師觀點（嘗試抓四位來賓名字在字幕中的觀點）
    analysts = ['毓棠', '庭皓', '俊敏', '正華']
    analyst_views = {}
    for analyst in analysts:
        if analyst in text:
            # 找分析師說話的段落
            idx = text.find(analyst)
            snippet = text[max(0, idx-50):min(len(text), idx+200)]
            snippet = re.sub(r'\s+', ' ', snippet).strip()
            analyst_views[analyst] = f"見節目內容：{snippet[:80]}..."
    if analyst_views:
        data['分析師觀點'] = analyst_views

    return data


if __name__ == '__main__':
    main()
