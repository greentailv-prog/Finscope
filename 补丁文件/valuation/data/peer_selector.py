"""可比公司选择（v3.1）：用户确认名单优先；否则仅使用可解释的行业池。
未识别行业、转型并购企业或取数失败，停止自动同业估值。
`_proxy_peers` 仅保留为旧版诊断代码，不再进入默认选择路径。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import median

from ..core import defaults
from ..core.metrics import normalize_name
from ..core.models import Company, Financials, Peer
from . import akshare_provider as ak


def _fetch_one(ticker: str) -> dict:
    try:
        return ak.fetch_peer(ticker)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ticker": ticker, "error": f"{type(exc).__name__}: {exc}"}


def _to_peer(raw: dict, reason: str = "", tier: str = "curated") -> Peer:
    return Peer(
        name=normalize_name(raw.get("name") or raw.get("ticker")),
        ticker=raw.get("ticker") or "",
        industry=raw.get("industry") or "",
        pe=raw.get("pe"), pe_forward=raw.get("pe_forward"), pb=raw.get("pb"),
        ps=raw.get("ps"), pcf=raw.get("pcf"), peg=raw.get("peg"),
        ev_revenue=raw.get("ev_revenue"), ev_ebitda=raw.get("ev_ebitda"),
        ev_ebit=raw.get("ev_ebit"),
        revenue_growth=raw.get("revenue_growth"),
        net_income_growth=raw.get("net_income_growth"),
        gross_margin=raw.get("gross_margin"),
        ebitda_margin=raw.get("ebitda_margin"),
        ebit_margin=raw.get("ebit_margin"),
        roe=raw.get("roe"),
        market_cap=raw.get("market_cap"), net_debt=raw.get("net_debt"),
        ebitda=raw.get("ebitda"), ebit=raw.get("ebit"),
        revenue=raw.get("revenue"), net_income=raw.get("net_income"),
        equity=raw.get("equity"), cfo=raw.get("cfo"),
        selection_reason=reason or raw.get("selection_reason") or "",
        tier=tier, caliber=raw.get("caliber") or "LYR",
        source=raw.get("source") or "", as_of=raw.get("as_of") or "",
        data_ok=bool(raw.get("data_ok", True)),
    )


def _curated_peers(company: Company, fin: Financials, limit: int = 6) -> dict | None:
    theme = defaults.match_theme(company.industry, company.business)
    if not theme:
        return None
    pool = defaults.theme_peers(theme)
    if not pool:
        return None
    target = str(company.ticker or "").strip()
    chosen = []
    for p in pool:
        code = str(p.get("code") or "").strip()
        if not code or code == target:
            continue
        chosen.append((code, p.get("name"), p.get("reason") or ""))
        if len(chosen) >= limit:
            break
    if not chosen:
        return None
    raws = {}
    with ThreadPoolExecutor(max_workers=2) as pool_ex:
        futures = {pool_ex.submit(_fetch_one, code): (code, name, reason)
                   for code, name, reason in chosen}
        for fut in as_completed(futures):
            code, name, reason = futures[fut]
            raws[code] = (fut.result(), name, reason)
    peers, missing = [], []
    for code, name, reason in chosen:
        raw, _, reason = raws.get(code, ({}, name, reason))
        if not raw.get("ok"):
            missing.append({"ticker": code, "name": name,
                            "reason": raw.get("error") or "取数失败"})
            continue
        p = _to_peer(raw, reason=reason, tier="curated")
        if not p.name or p.name == p.ticker:
            p.name = name or p.ticker
        peers.append(p)
    return {
        "peers": peers,
        "theme": theme,
        "sector": defaults.theme_sector(theme),
        "tier": "curated",
        "selection_note": f"按行业「{company.industry or theme}」匹配到配置池「{theme}」，"
                          f"逐家披露选取理由；剔除标的后取 {len(peers)} 家。",
        "missing": missing,
    }


def _proxy_peers(company: Company, limit: int = 5) -> dict:
    industry = company.industry or ""
    if any(k in industry for k in ("食品", "饮料", "酒", "乳", "调味", "零售", "农业", "纺织")):
        theme = "食品饮料"
        note = "行业未精确匹配，使用消费板块代理样本（低置信度）"
    elif any(k in industry for k in ("银行", "保险", "证券")):
        theme = "银行"
        note = "金融行业未精确匹配，使用银行代理样本（低置信度）"
    elif any(k in industry for k in ("电子", "半导体", "软件", "通信", "计算机")):
        theme = "软件"
        note = "科技行业未精确匹配，使用软件/科技代理样本（低置信度）"
    elif any(k in industry for k in ("医药", "医疗", "生物")):
        theme = "医药"
        note = "医药行业未精确匹配，使用医药代理样本（低置信度）"
    else:
        theme = "机械"
        note = "行业未识别，使用制造板块代理样本（低置信度）"
    pool = defaults.theme_peers(theme)[:limit]
    raws = {}
    with ThreadPoolExecutor(max_workers=2) as pool_ex:
        futures = {pool_ex.submit(_fetch_one, p["code"]): p for p in pool
                   if p.get("code") and p["code"] != company.ticker}
        for fut in as_completed(futures):
            p = futures[fut]
            raws[p["code"]] = (fut.result(), p)
    peers, missing = [], []
    for p in pool:
        code = p.get("code")
        if not code or code == company.ticker:
            continue
        raw, meta = raws.get(code, ({}, p))
        if not raw.get("ok"):
            missing.append({"ticker": code, "name": p.get("name"), "reason": raw.get("error")})
            continue
        peers.append(_to_peer(raw, reason=f"{note}；{p.get('reason') or ''}", tier="proxy"))
    return {"peers": peers, "theme": theme, "sector": "代理", "tier": "proxy",
            "selection_note": note, "missing": missing}


def select_peers(company: Company, fin: Financials,
                 user_peers: list | None = None,
                 user_peer_set: list[str] | None = None,
                 limit: int = 6) -> dict:
    """返回 {peers, tier, theme, selection_note, missing, warnings}。"""
    warnings = []
    # 1) 使用者直接给了带倍数的 peers
    if user_peers:
        peers = []
        for item in user_peers:
            if isinstance(item, Peer):
                p = item
            else:
                p = Peer.from_dict(item)
            p.tier = p.tier or "user"
            p.selection_reason = p.selection_reason or "使用者指定可比公司"
            peers.append(p)
        return {
            "peers": peers,
            "tier": "user",
            "theme": "使用者指定",
            "sector": "",
            "selection_note": f"使用者指定 {len(peers)} 家可比公司；系统只校验数据完整性，不替换名单。",
            "missing": [],
            "warnings": warnings,
        }

    # 2) 使用者给了代码
    if user_peer_set:
        raws = {}
        with ThreadPoolExecutor(max_workers=2) as pool_ex:
            futures = {pool_ex.submit(_fetch_one, code): code for code in user_peer_set}
            for fut in as_completed(futures):
                code = futures[fut]
                raws[code] = fut.result()
        peers, missing = [], []
        for code in user_peer_set:
            raw = raws.get(code, {})
            if not raw.get("ok"):
                missing.append({"ticker": code, "name": "", "reason": raw.get("error")})
                continue
            peers.append(_to_peer(raw, reason="使用者指定代码", tier="user"))
        if peers:
            return {
                "peers": peers, "tier": "user", "theme": "使用者指定",
                "sector": "", "selection_note": f"使用者指定代码，成功取到 {len(peers)} 家。",
                "missing": missing, "warnings": warnings,
            }
        return {
            "peers": [], "tier": "user_failed", "theme": "使用者指定", "sector": "",
            "selection_note": "指定同业均未取得有效行情，禁止静默换成其他公司。",
            "missing": missing,
            "warnings": warnings + ["使用者指定的可比公司取数全部失败，Comps 已暂停，请修复数据或调整名单。"],
        }

    # 3) 业务发生重大变化时，不允许仅凭旧行业标签自动锁定老业务同业。
    industry = (company.industry or "").lower()
    business = (company.business or "").lower()
    emerging = ("硅光", "光电子", "cpo", "光通信", "光子", "光模块", "chiplet", "先进封装")
    if (company.ticker == "300757" or
            (any(k in business for k in emerging) and
             any(k in industry for k in ("机械", "设备", "专用", "光伏", "自动化")))):
        from ..research.peer_registry import research
        peer_research = research(company.ticker) if company.ticker == "300757" else {}
        return {
            "peer_research":peer_research,
            "peers": [], "tier": "review_required", "theme": None, "sector": "",
            "selection_note": "存在转型/跨业务设备价值驱动因素：需按分部产品和客户核验纯业务同业。",
            "missing": [], "warnings": ["旧行业分类不能替代新业务的业务可比性审查；请提供经核验的 peer_set。"],
        }
    # 4) 可验证的预设行业池
    curated = _curated_peers(company, fin, limit=limit)
    if curated and curated["peers"]:
        if curated["missing"]:
            warnings.append(f"行业池中 {len(curated['missing'])} 家取数失败，已用剩余样本。")
        return {**curated, "warnings": warnings}

    # 不以行业大类的上市公司凑同业，尤其不把软件/机械/银行代理当纯业务样本。
    return {
        "peers": [], "tier": "none", "theme": None, "sector": "",
        "selection_note": "未建立可核验的同业池，不使用板块代理样本。",
        "missing": [],
        "warnings": warnings + ["无直接可比公司：Comps 不可用，待人工核验业务匹配和行情口径。"],
    }


def segment_peer_multiple(segment_name: str, max_peers: int = 4,
                          cache: dict | None = None) -> dict:
    """为一个分部找纯业务同业，返回中位倍数与样本。"""
    cache = cache if cache is not None else {}
    theme = defaults.sotp_theme(segment_name) or defaults.match_theme(segment_name)
    if not theme:
        return {"ok": False, "theme": None, "reason": f"分部「{segment_name}」未匹配到同业主题",
                "peers": [], "medians": {}}
    pool = defaults.theme_peers(theme)[:max_peers]
    raws = {}
    with ThreadPoolExecutor(max_workers=2) as pool_ex:
        futures = {}
        for p in pool:
            code = p.get("code")
            if not code:
                continue
            if code in cache:
                raws[code] = (cache[code], p)
            else:
                futures[pool_ex.submit(_fetch_one, code)] = p
        for fut in as_completed(futures):
            p = futures[fut]
            raw = fut.result()
            raws[p["code"]] = (raw, p)
            cache[p["code"]] = raw
    peers = []
    for p in pool:
        raw, meta = raws.get(p.get("code"), ({}, p))
        if raw.get("ok"):
            peers.append(_to_peer(raw, reason=meta.get("reason") or "", tier="curated"))
    def med(key):
        vals = [getattr(x, key) for x in peers if getattr(x, key) not in (None, 0)]
        vals = [v for v in vals if v > 0]
        return median(vals) if vals else None
    return {
        "ok": len(peers) >= 2,
        "theme": theme,
        "peers": peers,
        "peer_names": [p.name for p in peers],
        "peer_tickers": [p.ticker for p in peers],
        "medians": {
            "ev_revenue": med("ev_revenue"),
            "ev_ebitda": med("ev_ebitda"),
            "ev_ebit": med("ev_ebit"),
            "pe": med("pe"),
            "ps": med("ps"),
            "pb": med("pb"),
        },
    }
