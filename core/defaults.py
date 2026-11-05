"""配置读取与行业匹配。配置是产品规则的一部分，集中放 config/。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


@lru_cache(maxsize=1)
def sector_params() -> dict:
    return json.loads((CONFIG_DIR / "sector_params.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def industry_peers() -> dict:
    return json.loads((CONFIG_DIR / "industry_peers.json").read_text(encoding="utf-8"))


def market_defaults(market: str = "A") -> dict:
    return sector_params()["market_defaults"].get(market, sector_params()["market_defaults"]["A"])


def tax_clamp() -> dict:
    return sector_params()["tax_clamp"]


def peer_rules() -> dict:
    return sector_params()["peer_rules"]


def wacc_rules() -> dict:
    return sector_params()["wacc_reconciliation"]


def scenario_deltas() -> dict:
    return sector_params()["scenario_deltas"]


def size_premium(market_cap: float | None) -> tuple[float, str]:
    if not market_cap:
        return 0.0, "市值缺失，规模溢价按 0 处理"
    for row in sector_params()["size_premium"]:
        if market_cap >= row["min_market_cap"]:
            return row["premium"], f"市值 {market_cap / 1e8:,.0f} 亿元 → {row['label']}"
    return 0.0, "规模溢价 0"


def _contains_any(text: str, keywords: list[str]) -> bool:
    text = text or ""
    return any(k and k in text for k in keywords)


def match_theme(industry: str, business: str = "") -> str | None:
    """把行业/业务描述映射到配置里的可比公司主题。"""
    text = f"{industry or ''} {business or ''}"
    cfg = industry_peers()
    # 先匹配更具体的行业关键词，再匹配宽泛词
    candidates = []
    for row in cfg.get("industry_keyword_map", []):
        for kw in row.get("keywords", []):
            if kw and kw in text:
                candidates.append((len(kw), row["theme"]))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def theme_peers(theme: str) -> list[dict]:
    return list((industry_peers().get("themes", {}).get(theme) or {}).get("peers") or [])


def theme_sector(theme: str) -> str:
    return (industry_peers().get("themes", {}).get(theme) or {}).get("sector", "制造")


def sotp_theme(segment_name: str) -> str | None:
    """分部名称 → 纯业务同业主题。"""
    text = segment_name or ""
    best = None
    for row in industry_peers().get("sotp_keyword_map", []):
        for kw in row.get("keywords", []):
            if kw and kw in text:
                if best is None or len(kw) > best[0]:
                    best = (len(kw), row["theme"])
    return best[1] if best else None


def sector_proxy(theme_or_sector: str) -> str | None:
    cfg = industry_peers().get("sector_proxy", {})
    theme = theme_or_sector or ""
    if theme in cfg:
        return cfg[theme]
    # 如果传进来的是具体主题，先找它的 sector
    sector = (industry_peers().get("themes", {}).get(theme) or {}).get("sector")
    return cfg.get(sector) if sector else None


def industry_gate(industry: str, business: str = "") -> dict:
    text = f"{industry or ''} {business or ''}"
    for gate in sector_params().get("industry_gates", []):
        if _contains_any(text, gate.get("keywords", [])):
            return gate
    if not (industry or "").strip():
        return {
            "support": "limited",
            "reason": "行业未识别，估值按通用口径，仅供参考。",
            "alternatives": ["comps"],
            "primary_absolute": "dcf",
        }
    return {
        "support": "supported",
        "reason": "行业适用标准估值方法。",
        "alternatives": ["dcf", "comps"],
        "primary_absolute": "dcf",
    }


def sector_anchor(industry: str, business: str = "") -> dict | None:
    text = f"{industry or ''} {business or ''}"
    best = None
    for row in sector_params().get("sector_anchors", []):
        for kw in row.get("keywords", []):
            if kw and kw in text:
                if best is None or len(kw) > best[0]:
                    best = (len(kw), row)
    return best[1] if best else None


def multiple_meta(key: str) -> dict:
    return (sector_params().get("multiple_applicability") or {}).get(key, {})
