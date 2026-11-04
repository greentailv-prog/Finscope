"""本地 JSON 缓存。行情/财报按日缓存，避免重复拉取。"""
from __future__ import annotations

import json
import time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


def _path(key: str) -> Path:
    safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in key)
    return CACHE_DIR / f"{safe}.json"


def get(key: str, ttl_seconds: int = 12 * 3600):
    path = _path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - payload.get("_cached_at", 0) > ttl_seconds:
        return None
    return payload.get("data")


def put(key: str, data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(key)
    path.write_text(json.dumps({"_cached_at": time.time(), "data": data},
                               ensure_ascii=False, default=str), encoding="utf-8")
    return path
