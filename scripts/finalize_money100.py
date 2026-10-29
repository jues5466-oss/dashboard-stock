#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
錢線百分百 Discord 摘要收尾工具（自動截字 + 送出 + 記錄）

用途：
  摘要 agent 把 4 則訊息寫成 JSON（list of 4 strings）後呼叫本腳本，
  由腳本負責：字數檢查 → 自動截字 → webhook GET 驗證 → POST 4 則 → 寫 send_log。
  避免「摘要寫完但沒送出」的半途失敗（2026/10/22 實際發生）。

用法：
  python3 finalize_money100.py messages.json 20261022

messages.json 格式：["第1則文字", "第2則文字", "第3則文字", "第4則文字"]

自動截字策略（依序嘗試，確保訊息不被破壞）：
  1. 移除 Markdown 強調符號 ** 以外的空白行合併
  2. 表格型訊息（以 ｜ 開頭的行）：從「最後一列」開始刪除（低優先度標的）
  3. 一般段落型訊息：從「最後一個完整段落」開始刪除
  4. 再不行：對最後一個段落做句子級截斷
  截字過程會記錄 log，避免無聲地砍掉重要內容。
"""
import json
import os
import sys
import time

import requests

MAXLEN = 1900
LOG = '/Volumes/AI_Drive/StockData_v2/data/money100/discord_send_log.jsonl'

# webhook 不硬編碼：從 repo 外部的憑證來源讀取（2026/10/29 遷移，
# 這樣本檔就能進版控，截字修正有版本保護）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from stockdev_config import get_secret
    WEBHOOK = get_secret('DISCORD_WEBHOOK_MONEY100')
except Exception:
    WEBHOOK = None
if not WEBHOOK:
    raise SystemExit('找不到 DISCORD_WEBHOOK_MONEY100（檢查 ~/.config/stockdev/secrets.json）')


def trim_table(msg):
    """表格型訊息：從最後一列開始刪（最後列通常是低優先度標的）"""
    lines = msg.split('\n')
    # 找出表格區段的起訖
    idx = [i for i, l in enumerate(lines) if l.strip().startswith('｜')]
    if not idx:
        return msg, False
    while len(msg) > MAXLEN and len(idx) > 1:
        del lines[idx[-1]]
        idx.pop()
        msg = '\n'.join(lines)
    return msg, True


def _blocks(msg):
    """依空行切成區塊 [(start_idx, end_idx, text), ...]"""
    lines = msg.split('\n')
    out = []
    cur = []
    start = 0
    for i, l in enumerate(lines):
        if l.strip():
            if not cur:
                start = i
            cur.append(l)
        else:
            if cur:
                out.append((start, i, '\n'.join(cur)))
                cur = []
    if cur:
        out.append((start, len(lines), '\n'.join(cur)))
    return out


def _is_table_block(text):
    """區塊是否含表格列（以 ｜ 開頭的行）"""
    for l in text.split('\n'):
        if l.strip().startswith('｜'):
            return True
    return False


def trim_paragraph(msg):
    """段落型訊息：刪掉「最後一個不含表格列的區塊」（尾端優先）

    含表格列的區塊交給 trim_table 處理（逐列刪，不會整段刪掉整張表）。
    第一個區塊通常是標題，永遠保留。
    """
    while len(msg) > MAXLEN:
        bl = _blocks(msg)
        if len(bl) <= 1:
            break
        start, end, text = bl[-1]
        if _is_table_block(text):
            break  # 尾端是表格 → 交給 trim_table
        lines = msg.split('\n')
        del lines[start:end]
        while lines and not lines[-1].strip():
            lines.pop()
        msg = '\n'.join(lines)
    return msg


def trim_tail_sentence(msg):
    """最後手段：把最後一段截斷到符合長度（保留前文）"""
    if len(msg) <= MAXLEN:
        return msg
    lines = msg.split('\n')
    while len(msg) > MAXLEN and lines:
        last = lines[-1]
        if not last.strip():
            lines.pop()
            continue
        if len(last) > 40:
            lines[-1] = last[:max(0, len(last) - (len(msg) - MAXLEN))]
        else:
            lines.pop()
        msg = '\n'.join(lines)
    return msg


SENT_END = '。！？'


def trim_tail_precise(msg):
    """優先做法：從尾端依句號切到剛好不超過 MAXLEN，保留最多內容。

    2026/10/29 實測：原本先做 trim_paragraph 會「整段」刪掉最後一個分析師區塊
    （1923 → 1252，砍掉 671 字，含整段「明哲 傳產三族群：塑化、鋼鐵、航運」）。
    改成先做句級精準截斷 —— 只超幾十字時只刪最後一句，不傷內容。
    找不到可行切點時回傳 None，交給後續的整段/表格策略。
    """
    if len(msg) <= MAXLEN:
        return msg
    for ch in SENT_END:
        idx = msg.rfind(ch)
        while idx != -1:
            cand = msg[:idx + 1]
            if len(cand) <= MAXLEN and len(cand) >= len(msg) * 0.6:
                return cand
            idx = msg.rfind(ch, 0, idx)
    return None


def trim_tail_bullets(msg):
    """逐條移除尾端的「→ 項目」或「｜ 表格列」。

    比 trim_paragraph 細一層：刪掉的是單一條列，不是整個分析師區塊。
    2026/10/29 使用者要求「盡量不要刪整段」，此層用來取代整段刪除。
    """
    lines = msg.split('\n')
    while len(msg) > MAXLEN and len(lines) > 2:
        j = len(lines) - 1
        while j > 1 and not lines[j].strip():
            j -= 1
        s = lines[j].strip()
        if not (s.startswith('→') or s.startswith('｜')):
            break
        del lines[j:]
        msg = '\n'.join(lines).rstrip()
        lines = msg.split('\n')
    return msg


def trim(msg, label):
    orig = len(msg)
    if orig <= MAXLEN:
        return msg, orig, orig, 'ok'
    # 由細到粗：句級 → 逐條列 → 表格列 → 整段（最後手段）
    m = trim_tail_precise(msg)
    if m is None:
        m = msg
    if len(m) > MAXLEN:
        m = trim_tail_bullets(m)
    if len(m) > MAXLEN:
        m, _ = trim_table(m)
    if len(m) > MAXLEN:
        m = trim_paragraph(m)
    m = trim_tail_sentence(m)
    if len(m) > MAXLEN:
        raise SystemExit('msg%s 無法壓到 %d 字（目前 %d）' % (label, MAXLEN, len(m)))
    return m, orig, len(m), 'trimmed'


def main():
    if len(sys.argv) < 2:
        print('用法: finalize_money100.py messages.json [DATE]')
        sys.exit(1)
    path = sys.argv[1]
    date = sys.argv[2] if len(sys.argv) > 2 else None

    with open(path, 'r', encoding='utf-8') as f:
        msgs = json.load(f)
    if not isinstance(msgs, list) or len(msgs) != 4:
        raise SystemExit('messages.json 必須是 4 則字串的 list')

    # 1) 字數檢查 + 自動截字
    out = []
    for i, m in enumerate(msgs, 1):
        m2, orig, now, how = trim(m, str(i))
        print('msg%d: %d -> %d (%s)' % (i, orig, now, how))
        out.append(m2)

    # 2) webhook GET 驗證（送出前必做，2026/10/21 踩過 401）
    g = requests.get(WEBHOOK, timeout=20)
    print('GET webhook -> %d' % g.status_code)
    if g.status_code != 200:
        raise SystemExit('Webhook 無效 (%d)，中止發送' % g.status_code)

    # 3) POST 4 則
    results = []
    for i, m in enumerate(out, 1):
        r = requests.post(WEBHOOK, json={'content': m}, timeout=25)
        results.append(r.status_code)
        print('send msg%d -> %d' % (i, r.status_code))
        time.sleep(1.5)

    # 4) 記錄
    if all(s == 204 for s in results):
        import datetime
        rec = {
            'datetime': datetime.datetime.now().isoformat(),
            'date': date or '',
            'messages': out,
        }
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print('LOGGED OK -> %s' % LOG)
    else:
        raise SystemExit('並非全部 204，未記錄：%s' % results)


if __name__ == '__main__':
    main()
