#!/usr/bin/env python3
"""
台股交易日判斷工具

資料來源：data/market_holidays.json（本地權威清單）
  - 固定國定假日：依 TWSE 年度休市表建立
  - 臨時休市（颱風假等）：由使用者告知後補登

用法：
    from trading_calendar import is_trading_day, holiday_reason
    if not is_trading_day():
        print("今日休市：", holiday_reason())
        sys.exit(0)
"""
import json
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLIDAY_FILE = os.path.join(BASE_DIR, "data", "market_holidays.json")

_cache: dict = {"mtime": None, "data": {}}


def _load_holidays() -> dict:
    """載入休市清單（依 mtime 快取，避免重複讀檔）。"""
    try:
        mtime = os.path.getmtime(HOLIDAY_FILE)
    except OSError:
        return {}
    if _cache["mtime"] != mtime:
        try:
            with open(HOLIDAY_FILE, "r", encoding="utf-8") as f:
                _cache["data"] = json.load(f).get("holidays", {})
        except (OSError, json.JSONDecodeError):
            _cache["data"] = {}
        _cache["mtime"] = mtime
    return _cache["data"]


def holiday_reason(date_str: str = None) -> str:
    """
    回傳該日的休市原因；若是交易日則回傳空字串。
    date_str 格式 'YYYY-MM-DD'，預設為今天。
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    d = datetime.strptime(date_str, "%Y-%m-%d")

    if d.weekday() >= 5:
        return "週末休市"

    return _load_holidays().get(date_str, "")


def is_trading_day(date_str: str = None) -> bool:
    """該日是否為台股交易日。"""
    return holiday_reason(date_str) == ""


def previous_trading_day(date_str: str = None) -> str:
    """回傳前一個交易日（YYYY-MM-DD）。"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    d = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
    for _ in range(30):
        if is_trading_day(d.strftime("%Y-%m-%d")):
            return d.strftime("%Y-%m-%d")
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def add_holiday(date_str: str, reason: str = "臨時休市") -> bool:
    """把某日加入休市清單（使用者告知臨時休市時使用）。"""
    data = _load_holidays()
    if date_str in data:
        return False
    data[date_str] = reason
    with open(HOLIDAY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"_comment": "台股休市日清單（YYYY-MM-DD → 休市原因）。固定國定假日由 TWSE 年度休市表建立；臨時休市（颱風假等）由使用者告知後補登。",
             "holidays": dict(sorted(data.items()))},
            f, ensure_ascii=False, indent=2,
        )
    _cache["mtime"] = None
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        add_holiday(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "臨時休市")
        print(f"✅ 已加入休市清單：{sys.argv[2]}")
    else:
        target = sys.argv[1] if len(sys.argv) > 1 else None
        r = holiday_reason(target)
        print(f"{target or '今天'}: {'休市（' + r + '）' if r else '交易日'}")
