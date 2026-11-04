"""A 股数据层（akshare：新浪财报 + 东方财富公司信息/主营构成 + 中债收益率）。

这一类只负责「把原始数据取回来并统一口径」，不做估值判断。
所有取数失败都返回结构化结果，由上层决定降级或补假设。
"""
from __future__ import annotations

import os
import time
from threading import Lock
from datetime import date, timedelta
from statistics import median

from . import cache
from .quote_fallback import code6, quote_tencent
from .sources import source

# Windows 系统代理会挡住部分财经接口
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")

MAX_YEARS = 8
_PUSH2_COOLDOWN_UNTIL = 0.0
_PUSH2_LOCK = Lock()


def _ak():
    import akshare as ak
    return ak


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return None if v != v else v
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in ("", "--", "-", "None", "nan", "NaN", "null"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_period(raw):
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(digits) < 8:
        return None
    try:
        return int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
    except ValueError:
        return None


def _annual_rows(df, date_col="报告日"):
    if df is None or df.empty or date_col not in df.columns:
        return []
    out = []
    for _, row in df.iterrows():
        p = _parse_period(row[date_col])
        if p and (p[1], p[2]) == (12, 31):
            out.append((p[0], row))
    out.sort(key=lambda x: x[0])
    return out[-MAX_YEARS:]


def _pick(row, names, scale=1.0):
    for name in names:
        if name in row.index:
            v = _num(row[name])
            if v is not None:
                return v * scale
    return None


def _em_symbol(code: str) -> str:
    code = str(code).strip().upper()
    for p in ("SH", "SZ", "BJ"):
        if code.startswith(p):
            code = code[len(p):]
    code = code.zfill(6)
    if code[0] == "6":
        return "SH" + code
    if code[0] in ("0", "3"):
        return "SZ" + code
    return "BJ" + code


def _sina_symbol(code: str) -> str:
    code = str(code).strip().lower()
    for p in ("sh", "sz", "bj"):
        if code.startswith(p):
            code = code[len(p):]
    code = code.zfill(6)
    if code[0] == "6":
        return "sh" + code
    if code[0] in ("0", "3"):
        return "sz" + code
    return "bj" + code


def company_list(use_cache: bool = True) -> list[dict]:
    """A 股代码/简称全表（用于搜索框），本地缓存 7 天。"""
    key = "a_code_name"
    if use_cache:
        cached = cache.get(key, ttl_seconds=7 * 24 * 3600)
        if cached:
            return cached
    try:
        df = _ak().stock_info_a_code_name()
        rows = [{"code": str(r["code"]).zfill(6),
                 "name": str(r["name"]).replace(" ", "").replace("　", "")}
                for _, r in df.iterrows()]
        cache.put(key, rows)
        return rows
    except Exception:  # noqa: BLE001
        return []


def search_companies(query: str, limit: int = 10) -> list[dict]:
    """按股票代码或公司简称搜索 A 股。"""
    q = str(query or "").strip().replace(" ", "").replace("　", "")
    if not q:
        return []
    rows = company_list()
    if not rows:
        return [{"code": q.zfill(6), "name": q, "market": "A", "note": "代码直查"}] if q.isdigit() else []
    exact, prefix, contains = [], [], []
    for r in rows:
        code, name = r["code"], r["name"]
        if q.isdigit():
            if code == q.zfill(6):
                exact.append(r)
            elif code.startswith(q.zfill(6)):
                prefix.append(r)
        else:
            if name == q:
                exact.append(r)
            elif name.startswith(q):
                prefix.append(r)
            elif q in name:
                contains.append(r)
    out = (exact + prefix + contains)[:limit]
    for r in out:
        r["market"] = "A"
    return out


def company_info(code: str, prefer_tencent: bool = False) -> dict:
    """东方财富优先；受限流影响时用腾讯行情兜底，严禁静默编造精确股本。

    同业数据优先走腾讯，避免并发请求东方财富 push2 导致 IP 限流。
    """
    global _PUSH2_COOLDOWN_UNTIL
    try:
        code = code6(code)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    key = f"info_{'tencent_' if prefer_tencent else ''}{code}"
    cached = cache.get(key, ttl_seconds=600)
    if cached:
        return cached
    if not prefer_tencent:
        exact = cache.get(key, ttl_seconds=6 * 3600)
        if exact and not exact.get("shares_estimated"):
            return exact

    def eastmoney():
        global _PUSH2_COOLDOWN_UNTIL
        with _PUSH2_LOCK:
            if time.monotonic() < _PUSH2_COOLDOWN_UNTIL:
                raise RuntimeError("东方财富 push2 正在限流冷却期，暂不重复请求")
            try:
                df = _ak().stock_individual_info_em(symbol=code)
            except Exception as exc:
                # 冷却期只针对推测为限流的异常，网络普通异常允许下次尝试。
                lower = f"{type(exc).__name__}: {exc}".lower()
                if 'ratelimit' in lower or 'rate limit' in lower or '限流' in lower:
                    _PUSH2_COOLDOWN_UNTIL = time.monotonic() + 300
                raise
        data = {str(row['item']): row['value'] for _, row in df.iterrows()}
        result = {
            "ok": True,
            "name": str(data.get("股票简称") or "").replace(" ", ""),
            "industry": str(data.get("行业") or ""),
            "price": _num(data.get("最新")),
            "shares_outstanding": _num(data.get("总股本")),
            "market_cap": _num(data.get("总市值")),
            "shares_estimated": False,
            "price_date": date.today().isoformat(),
            "price_source": "东方财富·公司信息",
            "listing_date": str(data.get("上市时间") or ""),
            "warnings": [],
        }
        if not (result['price'] and result['shares_outstanding']):
            raise ValueError('东方财富返回的股价或总股本缺失')
        return result

    tries = (('tencent', quote_tencent), ('eastmoney', eastmoney)) if prefer_tencent else (
        ('eastmoney', eastmoney), ('tencent', quote_tencent))
    errors = []
    for name, fn in tries:
        try:
            result = fn(code) if name == 'tencent' else fn()
            if name == 'tencent' and errors:
                result['warnings'] = list(result.get('warnings') or []) + [
                    '主行情数据源不可用：' + '；'.join(errors)[:230]
                ]
            cache.put(key, result)
            return result
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:140]}")
    return {'ok': False, 'error': '公司信息/备用行情均失败：' + '；'.join(errors)}


def _series(rows_map, years, names, absolute=False):
    out = []
    for y in years:
        row = rows_map.get(y)
        v = _pick(row, names) if row is not None else None
        if v is not None and absolute:
            v = abs(v)
        out.append(v)
    return out


def fetch_company(ticker: str, market: str = "A", use_cache: bool = True,
                  prefer_tencent: bool = False) -> dict:
    """取一家 A 股公司的财务、行情、行业。"""
    code = code6(ticker)
    key = f"company_{code}"
    if use_cache:
        cached = cache.get(key, ttl_seconds=12 * 3600)
        if cached:
            # v3 旧缓存若缺市价/股本，不能一直把错误行情重复返回 12 小时。
            fin_cache = cached.get('financials') or {}
            if cached.get('ok') and not (fin_cache.get('price') and
                    fin_cache.get('shares_outstanding') and fin_cache.get('market_cap')):
                repaired = company_info(code, prefer_tencent=prefer_tencent)
                if repaired.get('ok'):
                    for item in ('price', 'shares_outstanding', 'market_cap',
                                 'price_date', 'price_source'):
                        fin_cache[item] = repaired.get(item)
                    fin_cache.setdefault('data_notes', [])
                    if repaired.get('shares_estimated'):
                        note = '股本按腾讯财经总市值/股价推算，精度受总市值四舍五入影响，需核验。'
                        if note not in fin_cache['data_notes']:
                            fin_cache['data_notes'].append(note)
                    cached['name'] = cached.get('name') if cached.get('name') not in (None, '', code) else repaired.get('name', code)
                    cached['industry'] = cached.get('industry') or repaired.get('industry') or ''
                    cached['warnings'] = [w for w in cached.get('warnings', [])
                        if not any(k in str(w) for k in ('股本缺失，无法计算', '未取得股价/股本', '公司信息取数失败'))]
                    cached['warnings'].extend(repaired.get('warnings') or [])
                    if repaired.get('price_source', '').startswith('腾讯'):
                        src = source('腾讯财经·行情', '价格/总市值/估算股本',
                            as_of=repaired.get('price_date'),
                            note='股本由总市值/股价反推，非准确公告股本')
                        src.update({'source_url': repaired.get('source_url'),
                                    'source_type': 'online', 'source_field': 'fields[3]价格,fields[45]总市值(亿元)'})
                        cached.setdefault('sources', []).append(src)
                    cache.put(key, cached)
            return cached

    if market != "A":
        return {"ok": False, "error": "当前版本内置 A 股数据源；美股请由 D 传入 canonical 数据。"}

    warnings: list[str] = []
    sources: list[dict] = []
    try:
        ak = _ak()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"未安装 akshare：{exc}"}

    info = company_info(code, prefer_tencent=prefer_tencent)
    if not info.get("ok"):
        warnings.append(info.get("error") or "公司信息取数失败")
    else:
        warnings.extend(info.get('warnings') or [])

    def grab(name):
        try:
            df = ak.stock_financial_report_sina(stock=_sina_symbol(code), symbol=name)
            sources.append(source(f"新浪财经·{name}", "财务报表", official=False))
            return df
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{name}取数失败：{str(exc)[:80]}")
            return None

    income = grab("利润表")
    balance = grab("资产负债表")
    cash = grab("现金流量表")
    inc_rows = dict(_annual_rows(income))
    bal_rows = dict(_annual_rows(balance))
    cfs_rows = dict(_annual_rows(cash))
    years = sorted(inc_rows)
    if not years:
        return {"ok": False, "error": "没有取到任何年度财务数据（新浪接口可能不可用）",
                "warnings": warnings, "sources": sources}

    revenue = _series(inc_rows, years, ["营业总收入", "营业收入"])
    cogs = _series(inc_rows, years, ["营业成本"])
    gross_profit = [(r - c) if (r is not None and c is not None) else None
                    for r, c in zip(revenue, cogs)]
    operating_profit = _series(inc_rows, years, ["营业利润"])
    finance_expense = _series(inc_rows, years, ["财务费用"])
    ebit = []
    for op, fe in zip(operating_profit, finance_expense):
        ebit.append((op + fe) if op is not None and fe is not None else op)

    fin = {
        "years": years,
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "ebit": ebit,
        "pretax_income": _series(inc_rows, years, ["利润总额"]),
        "tax_provision": _series(inc_rows, years, ["所得税费用"]),
        "net_income": _series(inc_rows, years, ["净利润"]),
        "net_income_parent": _series(inc_rows, years, ["归属于母公司所有者的净利润"]),
        "interest_expense": _series(inc_rows, years, ["利息费用", "利息支出"]),
        "finance_expense": finance_expense,
        "eps": _series(inc_rows, years, ["基本每股收益"]),
        "sbc": [None] * len(years),
        "da": [None] * len(years),
        "capex": _series(cfs_rows, years, ["购建固定资产、无形资产和其他长期资产所支付的现金"], absolute=True),
        "delta_nwc": [None] * len(years),
        "cfo": _series(cfs_rows, years, ["经营活动产生的现金流量净额"]),
        "dividends_paid": _series(cfs_rows, years, ["分配股利、利润或偿付利息支付的现金"], absolute=True),
        "total_debt": None,
        "cash": None,
        "minority_interest": None,
        "preferred_stock": 0.0,
        "total_assets": None,
        "total_equity": None,
        "current_assets": None,
        "current_liabilities": None,
        "inventory": None,
        "receivables": None,
        "payables": None,
        "price": info.get("price"),
        "shares_outstanding": info.get("shares_outstanding"),
        "market_cap": info.get("market_cap"),
        "beta": None,
        "beta_note": "未计算个股 Beta；规则层使用行业锚点 Beta 并做 Blume 调整",
        "industry": info.get("industry", ""),
        "sector": "",
        "price_date": info.get("price_date") or date.today().isoformat(),
        "price_time": info.get("price_time") or "",
        "price_source": info.get("price_source") or "",
        "data_notes": [],
    }

    if info.get('shares_estimated'):
        fin['data_notes'].append('股本按腾讯财经总市值/股价推算，精度受总市值四舍五入影响，需核验。')

    # 折旧摊销：现金流量表补充资料
    for names in (["固定资产折旧、油气资产折耗、生产性生物资产折旧", "固定资产折旧"],
                  ["无形资产摊销"], ["长期待摊费用摊销"]):
        vals = _series(cfs_rows, years, names)
        if any(v is not None for v in vals):
            for i, v in enumerate(vals):
                if v is not None:
                    fin["da"][i] = (fin["da"][i] or 0.0) + abs(v)
    if not any(v is not None for v in fin["da"]):
        warnings.append("现金流量表未提供折旧摊销，模型将按收入比例或资本开支关系估算。")
        fin["data_notes"].append("折旧摊销缺失，已由规则估算")

    if years[-1] in bal_rows:
        row = bal_rows[years[-1]]
        short = _pick(row, ["短期借款"]) or 0.0
        long_ = _pick(row, ["长期借款"]) or 0.0
        bond = _pick(row, ["应付债券"]) or 0.0
        current_portion = _pick(row, ["一年内到期的非流动负债"]) or 0.0
        fin["total_debt"] = short + long_ + bond + current_portion
        fin["cash"] = _pick(row, ["货币资金"])
        fin["minority_interest"] = _pick(row, ["少数股东权益"])
        fin["total_assets"] = _pick(row, ["资产总计", "资产合计"])
        fin["total_equity"] = _pick(row, [
            "所有者权益(或股东权益)合计", "所有者权益（或股东权益）合计",
            "所有者权益合计", "股东权益合计", "股东权益", "所有者权益",
        ])
        if fin["total_equity"] is None:
            parent = _pick(row, ["归属于母公司股东的权益", "归属于母公司所有者权益合计",
                                 "归属于母公司所有者的权益"])
            minority = fin["minority_interest"] or 0.0
            if parent is not None:
                fin["total_equity"] = parent + minority
        fin["current_assets"] = _pick(row, ["流动资产合计"])
        fin["current_liabilities"] = _pick(row, ["流动负债合计"])
        fin["inventory"] = _pick(row, ["存货"])
        fin["receivables"] = _pick(row, ["应收账款", "应收票据及应收账款"])
        fin["payables"] = _pick(row, ["应付账款", "应付票据及应付账款"])

    # 营运资本变动：应收账款 + 存货 - 应付账款的同比变化
    if bal_rows:
        def pair(names):
            return [_pick(bal_rows[y], names) if bal_rows.get(y) is not None else None for y in years]
        ar = pair(["应收账款", "应收票据及应收账款"])
        inv = pair(["存货"])
        ap = pair(["应付账款", "应付票据及应付账款"])
        nwc = [(a or 0) + (i or 0) - (p or 0) for a, i, p in zip(ar, inv, ap)]
        fin["delta_nwc"] = [None] + [nwc[i] - nwc[i - 1] for i in range(1, len(nwc))]
        warnings.append("营运资本变动为「（应收账款＋存货−应付账款）的同比变化」近似值，"
                        "与现金流量表口径可能有差异。")
        fin["data_notes"].append("营运资本变动为资产负债表近似值")

    if fin["price"] is None:
        # 兜底：新浪行情
        try:
            import requests
            r = requests.get(f"https://hq.sinajs.cn/list={_sina_symbol(code)}",
                             headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
                             timeout=12)
            r.encoding = "gbk"
            payload = r.text.split('="', 1)[1].rstrip('";\n')
            parts = payload.split(",")
            if len(parts) > 3:
                fin["price"] = _num(parts[3])
                fin["price_source"] = "新浪财经·行情"
                if not fin["shares_outstanding"]:
                    warnings.append("股本缺失，无法计算市值；每股价值可能为空。")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"行情取数失败：{str(exc)[:70]}")

    if fin["market_cap"] is None and fin["price"] and fin["shares_outstanding"]:
        fin["market_cap"] = fin["price"] * fin["shares_outstanding"]

    if info.get('ok'):
        if info.get('price_source', '').startswith('腾讯'):
            src = source('腾讯财经·行情', '价格/总市值/估算股本',
                                  as_of=info.get('price_date'),
                                  note='股本由总市值/股价反推，非准确公告股本')
            src.update({'source_url': info.get('source_url'), 'source_type': 'online',
                        'source_field': 'fields[3]价格,fields[45]总市值(亿元)'})
            sources.append(src)
        else:
            sources.append(source('东方财富·公司信息', '行情/行业/股本', official=False))

    out = {
        "ok": True,
        "market": "A",
        "currency": "CNY",
        "code": code,
        "name": info.get("name") or code,
        "industry": info.get("industry", ""),
        "listing_date": info.get("listing_date", ""),
        "financials": fin,
        "sources": sources,
        "warnings": warnings,
    }
    if use_cache:
        cache.put(key, out)
    return out


def fetch_segments(ticker: str, use_cache: bool = True) -> dict:
    """东方财富「主营构成」：最新年报的按产品收入拆分。"""
    code = str(ticker).strip()
    for p in ("SH", "SZ", "BJ"):
        if code.upper().startswith(p):
            code = code[2:]
    code = code.zfill(6)
    key = f"segments_{code}"
    if use_cache:
        cached = cache.get(key, ttl_seconds=24 * 3600)
        if cached:
            return cached
    try:
        df = _ak().stock_zygc_em(symbol=_em_symbol(code))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"主营构成取数失败：{type(exc).__name__}: {exc}"}
    if df is None or df.empty:
        return {"ok": False, "error": "主营构成接口无数据"}

    # 选择最新年报（12-31）
    df = df.copy()
    df["_year"] = df["报告日期"].astype(str).str[:4]
    annual = df[df["报告日期"].astype(str).str.endswith("12-31")]
    if annual.empty:
        annual = df
    latest = str(annual["报告日期"].astype(str).max())
    annual = annual[annual["报告日期"].astype(str) == latest]
    product = annual[annual["分类类型"].astype(str).str.contains("产品")] if "分类类型" in annual.columns else annual
    if product.empty:
        product = annual

    rows = []
    for _, r in product.iterrows():
        name = str(r.get("主营构成") or "").strip()
        if not name or name in ("合计", "总计"):
            continue
        revenue = _num(r.get("主营收入"))
        cost = _num(r.get("主营成本"))
        gp = _num(r.get("主营利润"))
        if gp is None and revenue is not None and cost is not None:
            gp = revenue - cost
        share = _num(r.get("收入比例"))
        if share is not None and share > 1:
            share = share / 100
        if revenue is None or revenue <= 0:
            continue
        level = "child" if name.startswith("其中:") else "top"
        clean_name = name.replace("其中:", "").strip()
        parent = ""
        if level == "child" and "-" in clean_name:
            parent, clean_name = clean_name.split("-", 1)
            parent = parent.strip()
            clean_name = clean_name.strip()
        rows.append({
            "name": clean_name,
            "raw_name": name,
            "level": level,
            "parent": parent,
            "revenue": revenue,
            "cost": cost,
            "gross_profit": gp,
            "gross_margin": (gp / revenue) if (gp is not None and revenue) else _num(r.get("毛利率")),
            "revenue_share": share,
            "period": latest,
            "source": "东方财富·主营构成（年报附注口径）",
        })
    out = {
        "ok": True,
        "period": latest,
        "rows": rows,
        "source": source("东方财富·主营构成", "分部收入", as_of=latest[:10], official=False),
        "note": "主营构成为年报附注的简化口径；分部利润为收入/毛利，EBIT 由规则按毛利占比分摊。",
    }
    if use_cache:
        cache.put(key, out)
    return out


def fetch_peer(ticker: str) -> dict:
    """取一家可比公司的财务 + 行情，并算好倍数。"""
    # 同业使用腾讯行情优先，避免 4-6 家并发触发东方财富 push2 限流。
    data = fetch_company(ticker, prefer_tencent=True)
    if not data.get("ok"):
        return {"ok": False, "ticker": ticker, "error": data.get("error")}
    fin = data["financials"]
    revenue = _latest(fin.get("revenue"))
    net_income = _latest(fin.get("net_income"))
    ebit = _latest(fin.get("ebit"))
    da = _latest(fin.get("da"))
    cfo = _latest(fin.get("cfo"))
    equity = fin.get("total_equity")
    cap = fin.get("market_cap")
    debt = fin.get("total_debt") or 0.0
    cash = fin.get("cash") or 0.0
    minority = fin.get("minority_interest") or 0.0
    preferred = fin.get("preferred_stock") or 0.0
    ebitda = (ebit + (da or 0.0)) if ebit is not None else None
    ev = (cap + debt - cash + minority + preferred) if cap is not None else None

    rev_series = [v for v in (fin.get("revenue") or []) if v is not None]
    ni_series = [v for v in (fin.get("net_income") or []) if v is not None]
    rev_growth = (rev_series[-1] / rev_series[-2] - 1) if len(rev_series) >= 2 and rev_series[-2] else None
    ni_growth = (ni_series[-1] / ni_series[-2] - 1) if len(ni_series) >= 2 and ni_series[-2] else None

    def div(a, b):
        return a / b if (a is not None and b and b > 0) else None

    pe = div(cap, net_income)
    return {
        "ok": True,
        "ticker": data["code"],
        "name": data.get("name") or data["code"],
        "industry": data.get("industry", ""),
        "pe": pe,
        "pb": div(cap, equity),
        "ps": div(cap, revenue),
        "pcf": div(cap, cfo),
        "peg": (pe / (ni_growth * 100)) if (pe and ni_growth and ni_growth > 0) else None,
        "ev_revenue": div(ev, revenue),
        "ev_ebitda": div(ev, ebitda),
        "ev_ebit": div(ev, ebit),
        "revenue_growth": rev_growth,
        "net_income_growth": ni_growth,
        "gross_margin": div(_latest(fin.get("gross_profit")), revenue),
        "ebitda_margin": div(ebitda, revenue),
        "ebit_margin": div(ebit, revenue),
        "roe": div(net_income, equity),
        "market_cap": cap,
        "net_debt": (debt - cash) if cap is not None else None,
        "ebitda": ebitda,
        "ebit": ebit,
        "revenue": revenue,
        "net_income": net_income,
        "equity": equity,
        "cfo": cfo,
        "caliber": "LYR",
        "source": "新浪财经·年报 + 东方财富·行情",
        "as_of": date.today().isoformat(),
        "data_ok": bool(revenue and cap),
        "financials": fin,
    }


def _latest(series):
    for v in reversed(series or []):
        if v is not None:
            return v
    return None


def fetch_market_rates(market: str = "A", use_cache: bool = True) -> dict:
    """中债/美债 10 年期收益率。取不到时返回空 dict，由规则层用默认值。"""
    key = f"rates_{market}"
    if use_cache:
        cached = cache.get(key, ttl_seconds=12 * 3600)
        if cached:
            return cached
    try:
        start = (date.today() - timedelta(days=45)).strftime("%Y%m%d")
        df = _ak().bond_zh_us_rate(start_date=start)
        if df is None or df.empty:
            return {}
        col = "中国国债收益率10年" if market == "A" else "美国国债收益率10年"
        sub = df[["日期", col]].dropna()
        if sub.empty:
            return {}
        last = sub.iloc[-1]
        value = float(last[col]) / 100
        out = {
            "risk_free": value,
            "risk_free_as_of": str(last["日期"])[:10],
            "risk_free_source": f"{'中债' if market == 'A' else '美债'} 10 年期国债收益率（{str(last['日期'])[:10]}）",
        }
        cache.put(key, out)
        return out
    except Exception:  # noqa: BLE001
        return {}
