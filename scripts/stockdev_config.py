#!/usr/bin/env python3
"""StockData 憑證設定（此模組本身不含任何憑證值）。

取值優先序：
  1. 環境變數
  2. ~/.hermes/.env 與 ~/.hermes/profiles/stock-dev/.env
  3. ~/.config/stockdev/secrets.json

用法：
    from stockdev_config import get_secret
    DISCORD_WEBHOOK = get_secret("DISCORD_WEBHOOK_FINANCE")

為什麼需要這層：StockData_v2 的 GitHub 倉庫是 **公開**的，
API key 與 Discord webhook 硬編碼在腳本裡會直接外洩。
2026/10/29 遷移時已把憑證搬到 repo 之外。

新增憑證的步驟：
  1. 把值加到 ~/.config/stockdev/secrets.json（權限 600），或
  2. 加到 ~/.hermes/.env 的一行 KEY=value，或
  3. 在 crontab / launchd 環境中設定同名環境變數
"""
import json
import os

ENV_FILES = [
    os.path.expanduser("~/.hermes/profiles/stock-dev/.env"),
    os.path.expanduser("~/.hermes/.env"),
]
SECRETS_JSON = os.path.expanduser("~/.config/stockdev/secrets.json")


def _read_env_file(path):
    """解析 KEY=value 形式的 .env（支援註解、引號、export 前綴）。"""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                out[k.strip()] = v
    except OSError:
        pass
    return out


def _read_json():
    try:
        with open(SECRETS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_ENV = {}
for _p in ENV_FILES:
    _ENV.update(_read_env_file(_p))
_JSON = _read_json()


def get_secret(key, default=""):
    """取得憑證：環境變數 > .env > secrets.json > default。"""
    val = os.environ.get(key)
    if val:
        return val
    val = _ENV.get(key)
    if val:
        return val
    val = _JSON.get(key)
    if val:
        return val
    return default


def require_secret(key):
    """取得憑證，缺少時拋出可讀的錯誤訊息。"""
    val = get_secret(key)
    if not val:
        raise RuntimeError(
            f"缺少憑證 {key}。請加到 ~/.config/stockdev/secrets.json、"
            f"~/.hermes/.env，或設定同名環境變數。"
        )
    return val


if __name__ == "__main__":
    # 自我檢查：列出可取得的憑證名稱（不印出值）
    for k in ["MINIMAX_API_KEY", "DISCORD_WEBHOOK_FINANCE", "DISCORD_WEBHOOK_OI",
              "DISCORD_WEBHOOK_REVENUE", "DISCORD_WEBHOOK_MONEY100"]:
        v = get_secret(k)
        print(f"  {k}: {'OK (len=%d)' % len(v) if v else '✗ 未設定'}")
