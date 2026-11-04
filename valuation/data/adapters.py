"""输入适配：把 D 的统一对象 / 使用者 JSON 统一成 ValuationInput。

兼容三套来源：
  1. FinScope D 的 canonical 对象（company / financials / market_data / comparison）；
  2. 本模块自己的 v1 输入 JSON（company / financials / peers / sotp_segments）；
  3. 使用者只给代码（自动联网取数）。
"""
from __future__ import annotations

import os

from ..core.metrics import normalize_name
from ..core.models import (
    Assumptions, Company, Financials, Peer, Segment, ValuationInput,
)
from . import akshare_provider as ak
from . import official_provider as official
from . import web_provider as web
from .evidence import rows_from_evidence
from .peer_selector import select_peers
from .segments import build_segments, fallback_single_segment
from .sources import merge, source


_ALIASES = {
    "revenue": ("revenue", "operating_revenue", "total_revenue", "营业收入"),
    "cogs": ("cogs", "operating_cost", "cost_of_revenue", "营业成本"),
    "gross_profit": ("gross_profit", "毛利"),
    "ebit": ("ebit", "营业利润", "operating_income"),
    "pretax_income": ("pretax_income", "pretax_profit", "profit_before_tax", "利润总额"),
    "tax_provision": ("tax_provision", "income_tax_expense", "income_tax", "所得税费用"),
    "net_income": ("net_income", "net_profit", "净利润"),
    "net_income_parent": ("net_income_parent", "net_profit_parent", "attributable_net_income",
                          "归属于母公司所有者的净利润"),
    "interest_expense": ("interest_expense", "利息费用", "interest_expense_total"),
    "finance_expense": ("finance_expense", "财务费用"),
    "eps": ("eps", "basic_eps", "基本每股收益"),
    "da": ("da", "depreciation_amortization", "depreciation_and_amortization", "折旧摊销"),
    "capex": ("capex", "capital_expenditure", "资本开支"),
    "delta_nwc": ("delta_nwc", "change_in_working_capital", "营运资本变动"),
    "cfo": ("cfo", "operating_cash_flow", "net_cash_from_operating", "经营活动现金流量净额"),
    "dividends_paid": ("dividends_paid", "dividend_paid", "股利支付"),
}


def _pick(d: dict, key: str):
    for alias in _ALIASES.get(key, (key,)):
        if alias in d and d[alias] is not None:
            return d[alias]
    return None


def _series_from_records(records: list[dict]) -> dict:
    if not records:
        return {}
    records = sorted(records, key=lambda r: str(r.get("year") or r.get("年份") or r.get("period") or ""))
    years = []
    for r in records:
        raw = r.get("year") or r.get("年份") or r.get("period") or ""
        try:
            years.append(int(str(raw)[:4]))
        except ValueError:
            years.append(str(raw))
    out = {"years": years}
    for key in _ALIASES:
        out[key] = [_pick(r, key) for r in records]
    return out


def canonical_records_to_history(records: dict) -> dict:
    """把 ABC v2 的 42 科目记录映射为 C 的时间序列，绝不以 0 填充缺失值。

    统一对象 financials 中每项是 {value, series:{year:value}, scope, status,...}；
    P0 与 P1 单位都是元；只接受 scope=合并报表/合并，无论字段名如何。
    """
    if not isinstance(records, dict) or not any(
        isinstance(v, dict) and ("series" in v or "value" in v)
        for v in records.values()
    ):
        return records
    years = set()
    for rec in records.values():
        if isinstance(rec, dict):
            for y in (rec.get("series") or {}):
                if str(y)[:4].isdigit():
                    years.add(int(str(y)[:4]))
            if rec.get("period") and str(rec["period"])[:4].isdigit():
                years.add(int(str(rec["period"])[:4]))
    years = sorted(years)
    if not years:
        return {"years": []}

    def select(keys):
        for key in keys:
            item = records.get(key)
            if not isinstance(item, dict):
                continue
            if item.get("status") in ("not_found", "extraction_error", "not_applicable"):
                continue
            if item.get("scope") == "母公司报表" or item.get("basis") == "母公司":
                continue
            series = item.get("series") or {}
            arr = []
            for y in years:
                val = series.get(str(y), series.get(y))
                if val is None and str(item.get("period", ""))[:4] == str(y):
                    val = item.get("value")
                arr.append(val if isinstance(val, (int, float)) else None)
            return arr
        return [None] * len(years)

    out = {"years": years}
    for key, aliases in _ALIASES.items():
        out[key] = select(aliases)
    # A 的 P0 归一化键名与 C 的历史序列对齐
    for target, keys in {
        "ebit": ["operating_profit", "ebit"],
        "da": ["depreciation_amortization", "da"],
        "pretax_income": ["pretax_profit"],
        "tax_provision": ["income_tax_expense"],
        "cogs": ["operating_cost"],
        "capex": ["capex"],
        "net_income_parent": ["net_income_parent"],
    }.items():
        if not any(v is not None for v in out.get(target, [])):
            out[target] = select(keys)
    # BS 是年末存量值，最新一期优先；仅在四项完整时计算债务合计
    for key, aliases in {
        "cash": ["cash_and_equivalents", "cash"],
        "total_assets": ["total_assets"],
        "total_equity": ["total_equity", "equity_parent"],
        "current_assets": ["current_assets"],
        "current_liabilities": ["current_liabilities"],
        "inventory": ["inventory"],
        "receivables": ["accounts_receivable"],
        "payables": ["accounts_payable"],
        "minority_interest": ["minority_interest"],
        "preferred_stock": ["preferred_stock"],
    }.items():
        values = select(aliases)
        out[key] = next((v for v in reversed(values) if v is not None), None)
    debt_components = [select([k]) for k in (
        "short_term_borrowings", "current_portion_lt_debt",
        "long_term_borrowings", "bonds_payable")]
    current_debts = [next((v for v in reversed(a) if v is not None), None) for a in debt_components]
    direct_debt = select(["total_debt", "interest_bearing_debt"])
    direct_debt = next((v for v in reversed(direct_debt) if v is not None), None)
    out["total_debt"] = (direct_debt if direct_debt is not None else
                         sum(current_debts) if all(v is not None for v in current_debts) else None)
    # 经营营运资本只包含应收、存货、应付的经营性净额，不含现金/有息借款。
    ar, inv, ap = select(["accounts_receivable", "receivables"]), select(["inventory"]), select(["accounts_payable", "payables"])
    operating_nwc = [a + b - c if a is not None and b is not None and c is not None else None
                     for a, b, c in zip(ar, inv, ap)]
    existing_delta = select(["delta_nwc", "change_net_working_capital"])
    out["delta_nwc"] = [
        existing_delta[i] if existing_delta[i] is not None else
        (operating_nwc[i]-operating_nwc[i-1] if i > 0 and operating_nwc[i] is not None
         and operating_nwc[i-1] is not None else None)
        for i in range(len(years))
    ]
    return out


def financials_from_any(data) -> Financials:
    if not data:
        return Financials()
    if isinstance(data, list):
        data = _series_from_records(data)
    if not isinstance(data, dict):
        return Financials()
    if "history" in data and isinstance(data["history"], list):
        data = {**data, **_series_from_records(data["history"])}
    data = canonical_records_to_history(data)
    fin = Financials.from_dict({k: v for k, v in data.items() if k in Financials.__dataclass_fields__})
    # 别名补齐
    for key in _ALIASES:
        if not getattr(fin, key, None):
            value = _pick(data, key)
            if value is not None:
                setattr(fin, key, value)
    # EBIT 口径：如果只有 operating_profit，加回财务费用
    if not fin.ebit and data.get("operating_profit") is not None:
        op = data["operating_profit"]
        fe = data.get("finance_expense")
        if isinstance(op, list) and isinstance(fe, list):
            fin.ebit = [(o + f) if o is not None and f is not None else o for o, f in zip(op, fe)]
        else:
            fin.ebit = op
    # 毛利补齐
    if not fin.gross_profit and fin.revenue and fin.cogs:
        fin.gross_profit = [(r - c) if r is not None and c is not None else None
                            for r, c in zip(fin.revenue, fin.cogs)]
    # 现金流符号统一：capex 正数=流出
    if fin.capex:
        fin.capex = [abs(v) if v is not None else None for v in fin.capex]
    # 缓存/JSON 可能把年份写成字符串，统一回整数
    if fin.years:
        fin.years = [int(str(y)[:4]) if str(y)[:4].isdigit() else y for y in fin.years]
    return fin


def _company_from(data: dict) -> Company:
    company = Company.from_dict(data.get("company") or {})
    company.name = normalize_name(company.name)
    mkt = data.get("market_data") or {}
    if mkt:
        company.price_date = company.price_date or mkt.get("price_date") or ""
        company.price_time = company.price_time or mkt.get("price_time") or ""
        company.price_source = company.price_source or mkt.get("price_source") or ""
    if not company.industry:
        company.industry = (data.get("industry") or data.get("sector") or "")
    if not company.report_period:
        fin = data.get("financials") or {}
        years = fin.get("years") if isinstance(fin, dict) else None
        if years:
            company.report_period = f"{years[-1]}-12-31"
    return company


def _apply_market_data(fin: Financials, data: dict) -> None:
    mkt = data.get("market_data") or {}
    if not mkt:
        return
    if mkt.get("price") is not None:
        fin.price = mkt["price"]
    if mkt.get("shares_outstanding") is not None:
        fin.shares_outstanding = mkt["shares_outstanding"]
    if mkt.get("market_cap") is not None:
        fin.market_cap = mkt["market_cap"]
    if not fin.market_cap and fin.price and fin.shares_outstanding:
        fin.market_cap = fin.price * fin.shares_outstanding
    fin.price_date = mkt.get("price_date") or fin.price_date
    fin.price_time = mkt.get("price_time") or fin.price_time
    fin.price_source = mkt.get("price_source") or fin.price_source


def _peer_from_canonical(pf: dict, mkt: dict | None) -> Peer | None:
    """D 传 peer_financials + peer_market_data 时，C 自己算倍数，不再联网。"""
    raw = pf.get("financials") if isinstance(pf.get("financials"), dict) else pf
    fin = financials_from_any(raw)
    ticker = str(pf.get("ticker") or pf.get("code") or (mkt or {}).get("ticker") or "")
    if not ticker:
        return None
    mkt = mkt or {}
    price = mkt.get("price")
    shares = mkt.get("shares_outstanding")
    cap = mkt.get("market_cap") or ((price or 0) * (shares or 0) if price and shares else None)
    revenue = fin.latest(fin.revenue)
    ni = fin.latest(fin.net_income)
    ebit = fin.latest(fin.ebit)
    da = fin.latest(fin.da)
    cfo = fin.latest(fin.cfo)
    equity = fin.total_equity
    debt = fin.total_debt or 0.0
    cash = fin.cash or 0.0
    minority = fin.minority_interest or 0.0
    preferred = fin.preferred_stock or 0.0
    ebitda = (ebit + (da or 0.0)) if ebit is not None else None
    ev = (cap + debt - cash + minority + preferred) if cap is not None else None

    def div(a, b):
        return a / b if (a is not None and b and b > 0) else None

    revs = [v for v in (fin.revenue or []) if v is not None]
    nis = [v for v in (fin.net_income or []) if v is not None]
    rev_growth = (revs[-1] / revs[-2] - 1) if len(revs) >= 2 and revs[-2] else None
    ni_growth = (nis[-1] / nis[-2] - 1) if len(nis) >= 2 and nis[-2] else None
    pe = div(cap, ni)
    return Peer(
        name=normalize_name(pf.get("name") or ticker),
        ticker=ticker,
        industry=pf.get("industry") or "",
        pe=pe,
        pb=div(cap, equity),
        ps=div(cap, revenue),
        pcf=div(cap, cfo),
        peg=(pe / (ni_growth * 100)) if (pe and ni_growth and ni_growth > 0) else None,
        ev_revenue=div(ev, revenue),
        ev_ebitda=div(ev, ebitda),
        ev_ebit=div(ev, ebit),
        revenue_growth=rev_growth,
        net_income_growth=ni_growth,
        gross_margin=div(fin.latest(fin.gross_profit), revenue),
        ebitda_margin=div(ebitda, revenue),
        ebit_margin=div(ebit, revenue),
        roe=div(ni, equity),
        market_cap=cap,
        net_debt=(debt - cash) if cap is not None else None,
        ebitda=ebitda, ebit=ebit, revenue=revenue, net_income=ni,
        equity=equity, cfo=cfo,
        selection_reason=pf.get("selection_reason") or "D 传入的 peer_financials",
        tier="user", caliber=pf.get("caliber") or "LYR",
        source=pf.get("source") or "D 统一数据对象", as_of=pf.get("as_of") or "",
        data_ok=bool(revenue and cap),
    )


def _peer_inputs(data: dict) -> tuple[list, list[str]]:
    peers = []
    for p in data.get("peers") or []:
        if isinstance(p, Peer):
            peers.append(p)
        elif isinstance(p, dict):
            peers.append(Peer.from_dict(p))
    comparison = data.get("comparison") or {}
    for p in comparison.get("peers") or []:
        if isinstance(p, dict):
            peers.append(Peer.from_dict(p))

    # D canonical：peer_financials + peer_market_data
    mkt_by_ticker = {}
    for m in data.get("peer_market_data") or []:
        if isinstance(m, dict):
            key = str(m.get("ticker") or m.get("code") or "")
            if key:
                mkt_by_ticker[key] = m
    for pf in data.get("peer_financials") or []:
        if not isinstance(pf, dict):
            continue
        ticker = str(pf.get("ticker") or pf.get("code") or "")
        peer = _peer_from_canonical(pf, mkt_by_ticker.get(ticker))
        if peer is not None:
            peers.append(peer)

    seen = set()
    unique_peers = []
    for p in peers:
        key = str(p.ticker or p.name)
        if key in seen:
            continue
        seen.add(key)
        unique_peers.append(p)
    peers = unique_peers

    tickers = []
    for key in ("peer_set", "peer_tickers"):
        if data.get(key):
            tickers.extend([str(x) for x in data[key]])
    comparison = data.get("comparison") or {}
    if comparison.get("peer_set"):
        for x in comparison["peer_set"]:
            if isinstance(x, dict):
                tickers.append(str(x.get("ticker") or x.get("code") or ""))
            else:
                tickers.append(str(x))
    # D 可能传 peer_financials + peer_market_data
    for pf in data.get("peer_financials") or []:
        if isinstance(pf, dict):
            ticker = str(pf.get("ticker") or pf.get("code") or "")
            if ticker:
                tickers.append(ticker)
    tickers = [t for t in dict.fromkeys(tickers) if t]
    return peers, tickers


# A / D 可以把已经封装好的官方数据层注册进来，C 不再自己直连。
# 用法：
#   from valuation.data.adapters import register_provider
#   register_provider("a_data", fetch_company=my_fetch, fetch_segments=my_segments)
#   payload["data_source"] = "a_data"
_CUSTOM_PROVIDERS: dict[str, dict] = {}


def register_provider(name: str, fetch_company=None, fetch_segments=None) -> None:
    """注册外部数据源（A 的 iFinD/Choice 封装、D 的统一数据层等）。

    fetch_company(ticker, market) 应返回与 akshare_provider.fetch_company 相同结构；
    fetch_segments(ticker) 返回 {"ok","rows","source",...}。
    """
    _CUSTOM_PROVIDERS[name] = {"company": fetch_company, "segments": fetch_segments}


def normalize(payload: dict) -> tuple[ValuationInput, dict]:
    payload = payload or {}
    company = _company_from(payload)
    fin = financials_from_any(payload.get("financials"))
    _apply_market_data(fin, payload)
    if not company.ticker and payload.get("ticker"):
        company.ticker = str(payload["ticker"])
    if not company.market:
        company.market = "A" if str(company.ticker).isdigit() else "US"
    if not company.currency:
        company.currency = "CNY" if company.market == "A" else "USD"

    peers, peer_tickers = _peer_inputs(payload)
    segments = [Segment(**{k: v for k, v in s.items() if k in Segment.__dataclass_fields__})
                for s in (payload.get("segments") or payload.get("sotp_segments") or [])
                if isinstance(s, dict)]
    assumptions = Assumptions.from_dict(payload.get("assumptions"))
    method = payload.get("method_selection") or assumptions.method_selection or "auto"
    multiples = payload.get("relative_multiples") or assumptions.multiples or []
    inp = ValuationInput(
        company=company,
        financials=fin,
        peers=peers,
        peer_set=peer_tickers,
        segments=segments,
        segment_evidence=payload.get("segment_evidence"),
        assumptions=assumptions,
        method_selection=method,
        relative_multiples=multiples,
        sources=list(payload.get("sources") or []),
        market_data=dict(payload.get("market_data") or {}),
        meta=dict(payload.get("meta") or {}),
        fetch_data=bool(payload.get("fetch_data", True)),
        allow_web=bool(payload.get("allow_web", True)),
        data_source=str(payload.get("data_source") or "auto"),
        web_evidence=payload.get("web_evidence"),
        as_of=str(payload.get("as_of") or ""),
    )
    return inp, {"peer_tickers": peer_tickers}


_FLOW_FIELDS = (
    "revenue", "cogs", "gross_profit", "ebit", "pretax_income", "tax_provision",
    "net_income", "net_income_parent", "interest_expense", "finance_expense",
    "eps", "sbc", "da", "capex", "delta_nwc", "cfo", "dividends_paid",
)


def _trim_anomalous_last_year(fin: Financials) -> tuple[bool, str]:
    """营收与净利润同时同比下滑超过 40% 时，剔除最新一年的流量数据。

    这不是「美化数据」，而是免费源母公司/合并口径混用的已知问题（五粮液案例）。
    资产负债表仍保留最新一期；所有剔除都会写入警告与数据来源说明。
    """
    rev = fin.revenue or []
    ni = fin.net_income or []
    if len(rev) < 2 or not rev[-2] or rev[-1] is None:
        return False, ""
    rev_change = rev[-1] / rev[-2] - 1
    ni_change = (ni[-1] / ni[-2] - 1) if (len(ni) >= 2 and ni[-2] and ni[-1] is not None) else None
    if rev_change >= -0.40:
        return False, ""
    if ni_change is not None and ni_change >= -0.40:
        return False, ""
    year = fin.years[-1] if fin.years else "最新"
    for field in _FLOW_FIELDS:
        series = getattr(fin, field, None)
        if isinstance(series, list) and len(series) > 1:
            setattr(fin, field, series[:-1])
    if fin.years:
        fin.years = fin.years[:-1]
    note = (f"{year} 年营业收入同比 {rev_change:+.0%}、净利润同比 "
            f"{(ni_change or 0):+.0%}，判定为口径异常/一次性事项；已从流量预测中剔除该年，"
            f"改用 {fin.years[-1] if fin.years else '上一'} 年作为基准。资产负债表仍为最新一期。")
    fin.data_notes.append(note)
    return True, note


def _data_quality(fin: Financials) -> list[str]:
    """口径一致性检查：营收/净利同比跳变超过 40% 时告警。

    免费源存在母公司报表 vs 合并报表混用的问题（例如五粮液 2025 年营收
    只有 2024 年的 45%）。这里不擅自改数，只把异常年份标出来。
    """
    warnings = []
    for label, series in (("营业收入", fin.revenue), ("净利润", fin.net_income)):
        vals = [(i, v) for i, v in enumerate(series or []) if v is not None]
        for (i0, v0), (i1, v1) in zip(vals, vals[1:]):
            if v0 and v0 > 0:
                change = v1 / v0 - 1
                if change < -0.40 or change > 1.50:
                    year = fin.years[i1] if i1 < len(fin.years) else i1
                    warnings.append(
                        f"{label} {year} 年同比 {change:+.0%}，超过 ±40% 阈值，"
                        "疑似母公司/合并报表口径混用或一次性事项；请核对年报原文。"
                    )
    return warnings


def prepare(inp: ValuationInput, fetch: bool | None = None) -> tuple[ValuationInput, dict]:
    """补齐数据：公司财务、行情、同业、分部、利率。返回上下文。"""
    fetch = inp.fetch_data if fetch is None else fetch
    ctx = {
        "warnings": [],
        "sources": list(inp.sources or []),
        "peer_selection": {},
        "segment_meta": {},
        "segment_source": "",
        "fetched": [],
        "data_source_requested": inp.data_source or "auto",
        "data_source_used": "",
        "source_fallback": False,
    }

    if inp.financials.revenue:
        ctx["data_source_used"] = ctx["data_source_used"] or "canonical"

    # 0) Agent/D 复核后的网页证据包优先（不重新联网）
    if inp.web_evidence and not inp.financials.revenue:
        ev = inp.web_evidence
        if isinstance(ev.get("financials"), dict):
            inp.financials = financials_from_any(ev["financials"])
            ctx["data_source_used"] = "web_evidence"
        elif ev.get("pdf_path"):
            parsed = web.parse_annual_report(ev["pdf_path"], int(ev.get("report_year") or 0))
            if parsed.get("ok"):
                from .web_provider import _merge_year_data
                inp.financials = financials_from_any(_merge_year_data(parsed.get("years") or {}))
                ctx["data_source_used"] = "web_evidence_pdf"
        if ev.get("segments"):
            ctx["_web_segments"] = list(ev["segments"])
        for s in ev.get("sources") or []:
            ctx["sources"].append(s)

    # 1) 公司财务：官方源 → 联网年报 → akshare（按 data_source 选择）
    if fetch and inp.company.ticker and not inp.financials.revenue:
        source_pref = (inp.data_source or "auto").lower()
        data = None
        source_used = ""

        # 1-0) 外部注册的数据源（A 的 iFinD/Choice 封装）
        custom = _CUSTOM_PROVIDERS.get(source_pref)
        if custom and custom.get("company"):
            try:
                data = custom["company"](inp.company.ticker, inp.company.market or "A")
                if data and data.get("ok"):
                    source_used = source_pref
                else:
                    ctx["warnings"].append(f"外部数据源 {source_pref} 返回失败：{(data or {}).get('error')}")
                    data = None
            except Exception as exc:  # noqa: BLE001
                ctx["warnings"].append(f"外部数据源 {source_pref} 异常：{type(exc).__name__}: {exc}")
                data = None

        # 1a) iFinD：只在显式指定、或 A 已接入并打开 FINSCOPE_OFFICIAL=1 时启用
        wants_official = source_pref == "ifind" or (
            source_pref == "auto" and os.environ.get("FINSCOPE_OFFICIAL") == "1"
        )
        if wants_official:
            if source_pref == "ifind" or official.probe_ifind().get("available"):
                od = official.fetch_ifind(inp.company.ticker)
                if od.get("ok"):
                    data, source_used = od, "iFinD"
                else:
                    ctx["warnings"].append(f"iFinD 取数失败：{od.get('error')}")

        # 1b) Choice
        wants_official = source_pref == "choice" or (
            source_pref == "auto" and os.environ.get("FINSCOPE_OFFICIAL") == "1"
        )
        if data is None and wants_official:
            if source_pref == "choice" or official.probe_choice().get("available"):
                od = official.fetch_choice(inp.company.ticker)
                if od.get("ok"):
                    data, source_used = od, "Choice"
                else:
                    ctx["warnings"].append(f"Choice 取数失败：{od.get('error')}")

        # 1c) 联网年报（显式 web，或 auto 下 akshare 之后再兜底）
        if data is None and source_pref == "web":
            wd = web.fetch_company(inp.company.ticker, inp.company.market or "A",
                                   name=inp.company.name or "")
            if wd.get("ok"):
                data = {
                    "ok": True,
                    "financials": wd["financials"],
                    "segments": wd.get("segments") or [],
                    "sources": wd.get("sources") or [],
                    "warnings": wd.get("warnings") or [],
                    "name": wd.get("name") or inp.company.name,
                    "industry": inp.company.industry,
                }
                source_used = "web"
            else:
                ctx["warnings"].append(f"联网年报取数失败：{wd.get('error')}")

        # 1d) akshare（现有免费源；auto 的默认；web/官方源不可用时兜底）
        if data is None and source_pref != "canonical":
            data = ak.fetch_company(inp.company.ticker, inp.company.market or "A")
            if data.get("ok"):
                source_used = "akshare"

        if data and data.get("ok"):
            inp.financials = financials_from_any(data["financials"])
            inp.company.name = normalize_name(inp.company.name or data.get("name") or inp.company.ticker)
            inp.company.industry = inp.company.industry or data.get("industry") or ""
            inp.company.report_period = inp.company.report_period or (
                f"{inp.financials.years[-1]}-12-31" if inp.financials.years else "")
            ctx["sources"].extend(data.get("sources") or [])
            ctx["warnings"].extend(data.get("warnings") or [])
            if data.get("segments"):
                ctx["_web_segments"] = data["segments"]
            ctx["fetched"].append("financials")
            ctx["data_source_used"] = source_used
            if source_pref not in ("auto", source_used):
                ctx["source_fallback"] = True
                ctx["warnings"].append(
                    f"请求的数据源 {source_pref} 不可用，已回退到 {source_used}。"
                )
        else:
            ctx["warnings"].append(f"公司财务取数失败：{(data or {}).get('error')}")
            ctx["data_source_used"] = source_used or "none"
    # D 传入的行情是唯一权威：取完财务后必须重新覆盖，避免 C 自己另取一个价
    if inp.market_data:
        _apply_market_data(inp.financials, {"market_data": inp.market_data})
        inp.company.price_date = inp.market_data.get("price_date") or inp.company.price_date
        inp.company.price_time = inp.market_data.get("price_time") or inp.company.price_time
        inp.company.price_source = inp.market_data.get("price_source") or inp.company.price_source

    if fetch and inp.company.ticker and inp.company.market == "A":
        # 行情/行业可能仍缺
        if not inp.financials.market_cap or not inp.financials.price or not inp.financials.shares_outstanding:
            # 同一次估值不要仅因「行业缺失」就再次访问限流中的 push2。
            info = ak.company_info(inp.company.ticker, prefer_tencent=True)
            if info.get("ok"):
                # 如 C 自行取行情，则价格、市值、股本必须来自同一份报价快照。
                inp.financials.price = info.get("price") or inp.financials.price
                inp.financials.shares_outstanding = info.get("shares_outstanding") or inp.financials.shares_outstanding
                inp.financials.market_cap = info.get("market_cap") or inp.financials.market_cap
                inp.financials.price_date = info.get('price_date') or inp.financials.price_date
                inp.financials.price_source = info.get('price_source') or inp.financials.price_source
                inp.company.industry = inp.company.industry or info.get("industry") or ""
                ctx['warnings'].extend(info.get('warnings') or [])
                ctx["fetched"].append("market_data")
        # D 传入的行情优先，不覆盖

    # 1.5) 不删除异常年份：先留原始历史数据，超阈值进入待核验队列。
    quality = _data_quality(inp.financials)
    ctx["warnings"].extend(quality)
    ctx["data_review_required"] = bool(quality and (inp.data_source or "").lower() != "canonical")
    if quality:
        inp.financials.data_notes.extend(quality)

    # 2) 资金成本
    if fetch and inp.company.market == "A":
        rates = ak.fetch_market_rates("A")
        if rates:
            ctx["market_rates"] = rates

    # 3) 同业
    if inp.peers:
        ctx["peer_selection"] = {
            "peers": inp.peers,
            "tier": "user",
            "theme": "使用者指定",
            "selection_note": f"使用者提供 {len(inp.peers)} 家可比公司。",
            "missing": [],
            "warnings": [],
        }
    elif fetch and (inp.data_source or "").lower() != "canonical":
        sel = select_peers(inp.company, inp.financials, None, inp.peer_set or None)
        inp.peers = sel.get("peers") or []
        ctx["peer_selection"] = sel
        ctx["warnings"].extend(sel.get("warnings") or [])
        ctx["fetched"].append("peers")

    # 4) 分部
    if inp.segments:
        ctx["segment_meta"] = {"coverage": None, "source": "使用者/D 提供"}
        ctx["segment_source"] = "使用者/D 提供"
    elif inp.segment_evidence:
        raw, evidence_source = rows_from_evidence(inp.segment_evidence)
        inp.segments, meta = build_segments(raw or [], inp.financials)
        ctx["segment_meta"] = meta
        ctx["segment_source"] = evidence_source or "证据包"
        if inp.segment_evidence.get("source"):
            ctx["sources"].append(inp.segment_evidence["source"])
        ctx["sources"].append(source(evidence_source or "年报分部证据", "分部收入",
                                     as_of=str(inp.segment_evidence.get("period") or "")[:10],
                                     official=False))
    elif ctx.get("_web_segments"):
        inp.segments, meta = build_segments(ctx["_web_segments"], inp.financials)
        ctx["segment_meta"] = meta
        ctx["segment_source"] = "联网年报·主营业务分产品"
        ctx["sources"].append(source("年报 PDF·主营业务分产品", "分部收入", official=True))
        ctx["fetched"].append("segments_web")
    elif (fetch and inp.company.ticker and inp.company.market == "A"
          and (inp.data_source or "").lower() != "canonical"):
        seg = ak.fetch_segments(inp.company.ticker)
        if seg.get("ok") and seg.get("rows"):
            inp.segments, meta = build_segments(seg["rows"], inp.financials)
            ctx["segment_meta"] = meta
            ctx["segment_source"] = "东方财富·主营构成"
            ctx["sources"].append(seg.get("source") or source("东方财富·主营构成", "分部收入"))
            ctx["fetched"].append("segments")
        else:
            inp.segments = []
            ctx["segment_meta"] = {"coverage": None, "fallback": False, "review_required": True}
            ctx["segment_source"] = "缺少分部原始披露"
            ctx["warnings"].append(f"分部数据未取到：{seg.get('error')}；SOTP 暂停，不伪造整体分部。")
    else:
        inp.segments = []
        ctx["segment_meta"] = {"coverage": None, "fallback": False, "review_required": True}
        ctx["segment_source"] = "缺少分部原始披露"

    # 5) 来源
    if inp.company.market == "A" and ctx.get("data_source_used") != "canonical":
        ctx["sources"].append(source("新浪财经·财务报表", "历史财务", official=False))
        ctx["sources"].append(source("东方财富·公司信息", "行情/行业/股本", official=False))
        if ctx.get("market_rates"):
            ctx["sources"].append(source(
                ctx["market_rates"].get("risk_free_source", "中债 10 年期国债收益率"),
                "无风险利率",
                as_of=ctx["market_rates"].get("risk_free_as_of"),
                official=True,
            ))
    ctx["sources"].append(source("Damodaran 国家风险溢价表", "ERP", official=True,
                                 note="取中国/美国市场对应值"))
    ctx["sources"] = merge(ctx["sources"])
    return inp, ctx
