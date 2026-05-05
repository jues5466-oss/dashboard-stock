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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
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
    if not episodes:
        print("❌ Playlist 中找不到指定日期的影片")
        sys.exit(1)

    print(f"  → 找到 {len(episodes)} 集:")
    for vid, title in episodes:
        print(f"    {vid}  {title[:50]}")

    # 下載每集字幕
    print(f"\n📥 開始下載字幕...")
    success_count = 0
    for video_id, title in episodes:
        if download_subs(video_id, date_str):
            success_count += 1

    print(f"\n✅ 完成！共 {success_count}/{len(episodes)} 集字幕下載成功")


if __name__ == '__main__':
    main()
