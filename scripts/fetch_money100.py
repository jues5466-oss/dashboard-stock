#!/usr/bin/env python3
"""
錢線百分百 - 字幕下載腳本
用途：每天 22:35 / 23:05 / 23:35 自動下載最新影片字幕
用法：
  python3 fetch_money100.py [日期 YYYYMMDD]
  若無日期參數，自動抓今天

⚠️ 字幕上傳時間：上集 22:30 / 中集 23:00 / 下集 23:30
   建議 cron 時間：22:40 fetch-1 / 23:10 fetch-2 / 23:40 fetch-3
"""
import subprocess
import sys
import os
import glob
from datetime import datetime

# 設定
BASE_DIR = '/Volumes/AI_Drive/StockData_v2/data/money100'
SUB_DIR  = f'{BASE_DIR}/subs'
PLAYLIST_URL = 'https://www.youtube.com/playlist?list=PLlAWMYbuVkC_x_Hfk6vuA8FhWicFgzCN6'

YTDLP = '/opt/homebrew/bin/yt-dlp'


def get_episodes_from_playlist(date_str):
    """從 playlist 取出指定日期的所有影片 ID"""
    cmd = [
        YTDLP, '--playlist-end', '20',
        '--print', '%(upload_date)s %(id)s %(title)s',
        '--no-download', PLAYLIST_URL
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        lines = result.stdout.strip().split('\n')
        episodes = []
        for line in lines:
            parts = line.split(' ', 2)
            if len(parts) >= 2 and parts[0] == date_str:
                video_id = parts[1]
                title = parts[2] if len(parts) > 2 else ''
                # 過濾「精彩搶先看」
                if '搶先看' not in title:
                    episodes.append((video_id, title))
        return episodes
    except Exception as e:
        print(f"  ⚠️ Playlist 讀取失敗: {e}")
        return []


def episode_tag(title):
    """從標題取出集數標記：上集 / 中集 / 下集 / 全集（None = 無法判斷）"""
    for tag in ('上集', '中集', '下集'):
        if tag in title:
            return tag
    if '完整版(全集)' in title or '完整版（全集）' in title:
        return '全集'
    return None


def dedupe_by_tag(episodes):
    """同一集可能有多個重複上傳（不同 video id），以集數標記去重

    保留第一個出現的（playlist 優先，序位在前）。
    """
    seen = {}
    out = []
    for vid, title in episodes:
        tag = episode_tag(title)
        if tag and tag in seen:
            continue
        if tag:
            seen[tag] = vid
        out.append((vid, title))
    return out


def get_episodes_from_search(date_str, known_ids):
    """降級：用 ytsearch 補抓 playlist 尚未更新的集數

    背景：YouTube playlist 更新有延遲，當天上/中/下集常只列出 2 集。
    用 ytsearch 搜尋「錢線百分百 YYYYMMDD完整版」補齊缺漏（已下載的不重複）。
    """
    if len(known_ids) >= 3:
        return []
    cmd = [
        YTDLP, '--playlist-end', '8',
        '--print', '%(upload_date)s|%(id)s|%(title)s',
        '--no-download',
        f'ytsearch8:錢線百分百 {date_str}完整版'
    ]
    found = []
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        for line in result.stdout.strip().split('\n'):
            parts = line.split('|')
            if len(parts) < 3:
                continue
            up, vid, title = parts[0], parts[1], parts[2]
            if up != date_str:
                continue
            if vid in known_ids:
                continue
            # 只收「錢線百分百」本頻道、且排除預告與其他節目
            if '錢線百分百' not in title:
                continue
            if '搶先看' in title or '少康戰情室' in title:
                continue
            found.append((vid, title))
    except Exception as e:
        print(f"  ⚠️ ytsearch 補抓失敗: {e}")
    return found


def download_subs(video_id, date_str):
    """下載單一影片的繁體中文字幕，回傳是否成功"""
    # 先刪除該日期的舊檔（同一 ID 的才保留）
    existing = glob.glob(f'{SUB_DIR}/{date_str}.{video_id}.*.vtt')
    if existing:
        print(f"  → 已有字幕: {existing[0]}")
        return True

    cmd = [
        YTDLP,
        '--write-subs', '--sub-lang', 'zh-Hant',
        '--skip-download',
        '--output', f'{SUB_DIR}/{date_str}.%(id)s.%(ext)s',
        f'https://www.youtube.com/watch?v={video_id}'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        matches = glob.glob(f'{SUB_DIR}/{date_str}.{video_id}.*.vtt')
        if not matches:
            # 降級：沒有手動 zh-Hant 字幕時，改抓自動生成字幕
            cmd_auto = cmd[:]
            cmd_auto[2] = '--write-auto-subs'
            result = subprocess.run(cmd_auto, capture_output=True, text=True, timeout=120)
            matches = glob.glob(f'{SUB_DIR}/{date_str}.{video_id}.*.vtt')
        if matches:
            size = os.path.getsize(matches[0])
            print(f"  → 下載成功: {matches[0]} ({size} bytes)")
            return True
        else:
            print(f"  → yt-dlp stderr: {result.stderr[-300:]}")
            return False
    except Exception as e:
        print(f"  ⚠️ 下載失敗: {e}")
        return False


def write_episode_map(date_str, episodes):
    """寫入 episode_map.json：{date: {tag: {video_id, file, bytes, title, topics}}}

    下載 job 依 YouTube 標題的 (上集)/(中集)/(下集) 標記判定集數，
    供摘要 job 直接對照（比檔案大小、內容開頭都可靠）。
    """
    import json
    map_path = f'{BASE_DIR}/episode_map.json'
    data = {}
    if os.path.exists(map_path):
        try:
            with open(map_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}

    entry = {}
    for vid, title in episodes:
        tag = episode_tag(title)
        if not tag:
            continue
        matches = glob.glob(f'{SUB_DIR}/{date_str}.{vid}.*.vtt')
        if not matches:
            continue
        entry[tag] = {
            'video_id': vid,
            'file': os.path.basename(matches[0]),
            'bytes': os.path.getsize(matches[0]),
            'title': title,
        }

    if entry:
        data[date_str] = entry
        with open(map_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  → episode_map.json 已更新: {list(entry.keys())}")
    else:
        print("  ⚠️ 無法判定集數標記，episode_map.json 未更新")


def main():
    if len(sys.argv) >= 2:
        date_str = sys.argv[1]
    else:
        date_str = datetime.now().strftime('%Y%m%d')

    print(f"\n📺 錢線百分百 字幕下載")
    print(f"   日期: {date_str}")
    print(f"   時間: {datetime.now().strftime('%H:%M:%S')}")

    os.makedirs(SUB_DIR, exist_ok=True)

    # 從 playlist 找指定日期的所有影片
    print(f"\n🔍 從 Playlist 搜尋 {date_str} 影片...")
    episodes = get_episodes_from_playlist(date_str)
    if episodes:
        print(f"  → 找到 {len(episodes)} 集:")
        for vid, title in episodes:
            print(f"    {vid}  {title[:50]}")
    else:
        print("⚠️ Playlist 中找不到指定日期的影片，改用 ytsearch 搜尋")

    # Playlist 更新有延遲 → 用 ytsearch 補抓缺漏的集數
    # ⚠️ 2026/10/23 修正：原本 playlist 為空就直接 sys.exit(1)，
    #    導致 ytsearch 降級路徑永遠走不到。改為 playlist 空也照跑降級。
    known = {vid for vid, _ in episodes}
    extra = get_episodes_from_search(date_str, known)
    if extra:
        print(f"  → ytsearch 補抓到 {len(extra)} 集:")
        for vid, title in extra:
            print(f"    {vid}  {title[:50]}")
        episodes += extra

    if not episodes:
        print(f"❌ 找不到 {date_str} 的任何影片（playlist + ytsearch 皆無結果）")
        print(f"   可能是當天尚未上傳，或已跨日 → 摘要 job 應降級改用前一天的字幕")
        sys.exit(2)

    episodes = dedupe_by_tag(episodes)

    # 下載每集字幕
    print(f"\n📥 開始下載字幕...")
    success_count = 0
    for video_id, title in episodes:
        if download_subs(video_id, date_str):
            success_count += 1

    print(f"\n✅ 完成！共 {success_count}/{len(episodes)} 集字幕下載成功")

    # 寫入集數對照表，供摘要 job 使用
    write_episode_map(date_str, episodes)


if __name__ == '__main__':
    main()
