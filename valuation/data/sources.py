"""来源台账：每条数据都记出处、取数日期、性质、用途。"""
from __future__ import annotations

from datetime import date


def source(name: str, purpose: str, as_of: str | None = None,
           official: bool = False, note: str = "") -> dict:
    return {
        "name": name,
        "purpose": purpose,
        "as_of": as_of or date.today().isoformat(),
        "official": bool(official),
        "note": note,
    }


def merge(sources: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for s in sources or []:
        key = (s.get("name"), s.get("purpose"), s.get("as_of"))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out
