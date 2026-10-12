"""三种估值方法：DCF、相对估值、分部估值（SOTP）。

方法论取自 finance-skills 的 company-valuation，做了两处适配：
  · 市场参数按 A股 / 美股 分别给默认值（原版只有美股口径）
  · 所有中间过程都显式返回，便于 Excel 底稿逐行还原
"""
from __future__ import annotations

import math
from statistics import median

from .models import Assumptions, Financials, Peer

# 各市场的默认参数。原版只给美国值，这里补上中国口径。
MARKET_DEFAULTS = {
    "A": {
        "risk_free": 0.018,      # 10 年期国债收益率（运行时用实际取到的值覆盖）
        "erp": 0.0514,           # Damodaran 中国国家风险溢价
        "terminal_growth_cap": 0.04,   # 中国长期名义 GDP 5–6%，永续 g 上限 4.0%
        "cost_of_debt": 0.035,   # 5 年期以上 LPR
    },
    "US": {
        "risk_free": 0.0428,
        "erp": 0.0428,           # Damodaran 美国隐含 ERP
        "terminal_growth_cap": 0.03,
        "cost_of_debt": 0.055,
    },
}


def _clean(seq):
    return [v for v in (seq or []) if v is not None]


def median_of(seq, default=None):
    vals = _clean(seq)
    return median(vals) if vals else default


def safe_div(a, b, default=None):
    try:
        if b in (None, 0):
            return default
        return a / b
    except (TypeError, ZeroDivisionError):
        return default


# ======================================================================
# WACC
# ======================================================================


def compute_wacc(fin: Financials, asm: Assumptions, market: str = "A") -> dict:
    """CAPM + 目标资本结构。返回每个分项，方便底稿逐格还原。"""
    defaults = MARKET_DEFAULTS.get(market, MARKET_DEFAULTS["A"])

    rf = asm.risk_free if asm.risk_free is not None else defaults["risk_free"]
    erp = asm.erp if asm.erp is not None else defaults["erp"]
    beta = asm.beta if asm.beta is not None else (fin.beta or 1.0)
    beta_source = ("手工指定" if asm.beta is not None
                   else ("数据源 Beta" if fin.beta else "缺失，兜底 1.0"))

    ke = rf + beta * erp + (asm.size_premium or 0.0)

    # 税率：优先用户给定；否则用近三年有效税率（中位数），夹在 15%–30%
    tax = asm.tax_rate
    tax_source = "手工指定"
    if tax is None:
        eff = [safe_div(t, p) for t, p in zip(fin.tax_provision or [], fin.pretax_income or [])
               if safe_div(t, p) is not None]
        med = median_of(eff[-3:])
        if med is not None:
            tax = min(0.30, max(0.15, med))
            tax_source = "近三年有效税率中位数（夹在 15%–30%）"
        else:
            tax = 0.21
            tax_source = "缺数据，兜底 21%"

    # 债务成本：优先「利息费用 ÷ 有息负债」
    kd = asm.cost_of_debt
    kd_source = "手工指定"
    if kd is None:
        eff_kd = safe_div(fin.interest_expense and fin.latest(fin.interest_expense), fin.total_debt)
        if eff_kd and 0 < eff_kd < 0.30:
            kd, kd_source = eff_kd, "利息费用 ÷ 有息负债"
        else:
            kd, kd_source = defaults["cost_of_debt"], f"{market} 市场默认值"
    kd = min(max(kd, 0.0), 0.30)

    # 资本结构：用市值口径
    e_value = fin.market_cap or 0.0
    d_value = fin.total_debt or 0.0
    if asm.target_debt_ratio is not None:
        d_ratio = asm.target_debt_ratio
        e_ratio = 1 - d_ratio
        capital_source = "手工指定目标资本结构"
    else:
        total = e_value + d_value
        e_ratio = safe_div(e_value, total, 1.0)
        d_ratio = 1 - e_ratio
        capital_source = "当前市值口径（E=市值，D=报表有息负债）"

    wacc = e_ratio * ke + d_ratio * kd * (1 - tax)

    # ---- 隐含资本成本反查 ----
    # 从当前市盈率倒推市场隐含的资本成本，用来发现 beta / ERP / 增速的输入错误。
    # 若算出来的 WACC 与市场隐含值差 300bp 以上，说明某个输入有问题。
    implied_ke = None
    implied_note = ""
    pe = None
    if fin.market_cap and fin.net_income and fin.latest(fin.net_income) and fin.latest(fin.net_income) > 0:
        pe = fin.market_cap / fin.latest(fin.net_income)
    if pe and pe > 0:
        earnings_yield = 1 / pe
        # 可持续增速用永续增长率近似
        implied_ke = earnings_yield + asm.terminal_growth
        gap = abs(wacc - implied_ke)
        implied_note = (
            f"由当前 PE（{pe:.1f} 倍）反推：盈利收益率 {earnings_yield:.2%} + "
            f"永续增速 {asm.terminal_growth:.2%} = 隐含资本成本 {implied_ke:.2%}；"
            + (f"与算出的 WACC（{wacc:.2%}）相差 {gap * 10000:.0f}bp，"
               + ("**超过 300bp，请核对 beta / ERP / 增速中哪一个偏了**"
                  if gap > 0.03 else "在可接受范围内。")
               )
        )

    return {
        "implied_cost_of_equity": implied_ke,
        "implied_cost_note": implied_note,
        "implied_pe": pe,
        "risk_free": rf,
        "erp": erp,
        "beta": beta,
        "beta_source": beta_source,
        "size_premium": asm.size_premium or 0.0,
        "cost_of_equity": ke,
        "cost_of_debt": kd,
        "cost_of_debt_source": kd_source,
        "tax_rate": tax,
        "tax_source": tax_source,
        "equity_ratio": e_ratio,
        "debt_ratio": d_ratio,
        "capital_source": capital_source,
        "wacc": wacc,
    }


# ======================================================================
# DCF
# ======================================================================


def _margin_series(fin: Financials, kind: str) -> float | None:
    """取近三年中位数的比率。None 表示数据不足。"""
    rev = fin.revenue or []
    pairs = {
        "ebit": fin.ebit,
        "da": fin.da,
        "capex": fin.capex,
        "nwc": fin.delta_nwc,
    }.get(kind)
    if not pairs:
        return None
    ratios = []
    for i, value in enumerate(pairs):
        if i >= len(rev):
            break
        r = safe_div(value, rev[i])
        if r is not None:
            ratios.append(abs(r) if kind in ("capex", "nwc") else r)
    return median_of(ratios[-3:])


def build_dcf(fin: Financials, asm: Assumptions, market: str = "A",
              peers: list[Peer] | None = None, _solve_implied: bool = True) -> dict:
    """5 年 FCFF 折现 + 终值（Gordon 与退出倍数取中点）。

    `_solve_implied=False` 用于隐含折现率反解的内部迭代——那一步会反复调本函数，
    必须断开递归，否则栈溢出。
    """
    peers = peers or []
    defaults = MARKET_DEFAULTS.get(market, MARKET_DEFAULTS["A"])
    warnings: list[str] = []

    rev_hist = _clean(fin.revenue)
    base_revenue = rev_hist[-1] if rev_hist else None
    if not base_revenue:
        return {"ok": False, "error": "缺少营业收入历史数据，无法建立 DCF"}

    # ---- 收入增速路径：首年 -> 永续，线性衰减 ----
    hist_cagr = None
    if len(rev_hist) >= 2 and rev_hist[0] > 0:
        hist_cagr = (rev_hist[-1] / rev_hist[0]) ** (1 / (len(rev_hist) - 1)) - 1

    y1 = asm.revenue_growth_y1 if asm.revenue_growth_y1 is not None else hist_cagr
    y1_source = "手工指定" if asm.revenue_growth_y1 is not None else "历史 CAGR"
    if y1 is None:
        y1, y1_source = 0.05, "数据不足，兜底 5%"
    y1 = max(min(y1, 1.0), -0.5)

    g_terminal = asm.terminal_growth
    cap = defaults["terminal_growth_cap"]
    if g_terminal > cap:
        warnings.append(
            f"永续增长率 {g_terminal:.2%} 超过 {market} 市场可辩护上限 {cap:.1%}，"
            f"已按上限处理。"
        )
        g_terminal = cap

    n = max(3, min(int(asm.forecast_years or 5), 10))
    if n != asm.forecast_years:
        warnings.append(f"预测期长度已从 {asm.forecast_years} 调整为 {n} 年（允许 3–10 年）。")
    growth_path = [y1 + (g_terminal - y1) * i / (n - 1) for i in range(n)] if n > 1 else [y1]

    # ---- 利润率 ----
    ebit_margin = asm.ebit_margin
    if ebit_margin is None:
        ebit_margin = _margin_series(fin, "ebit")
        ebit_margin_src = "近三年中位数"
    else:
        ebit_margin_src = "手工指定"
    if ebit_margin is None:
        # 用净利润率近似（缺 EBIT 时）
        ebit_margin = safe_div(fin.latest(fin.net_income), base_revenue, 0.10)
        ebit_margin_src = "缺 EBIT，用净利率近似"

    da_pct = asm.da_pct_revenue
    da_pct_src = "手工指定"
    if da_pct is None:
        da_pct = _margin_series(fin, "da")
        da_pct_src = "近三年中位数"
    if da_pct is None:
        da_pct, da_pct_src = 0.05, "缺数据，兜底 5%"

    capex_pct = asm.capex_pct_revenue
    capex_pct_src = "手工指定"
    if capex_pct is None:
        capex_pct = _margin_series(fin, "capex")
        capex_pct_src = "近三年中位数"
    if capex_pct is None:
        capex_pct, capex_pct_src = 0.06, "缺数据，兜底 6%"

    nwc_pct = asm.nwc_pct_revenue
    nwc_pct_src = "手工指定"
    if nwc_pct is None:
        nwc_pct = _margin_series(fin, "nwc")
        nwc_pct_src = "近三年中位数"
    if nwc_pct is None:
        nwc_pct, nwc_pct_src = 0.02, "缺数据，兜底 2%"

    # ---- WACC ----
    wacc_block = compute_wacc(fin, asm, market)
    wacc = wacc_block["wacc"]
    tax = wacc_block["tax_rate"]

    if wacc <= g_terminal:
        return {"ok": False,
                "error": f"WACC（{wacc:.2%}）不高于永续增长率（{g_terminal:.2%}），"
                         f"终值公式失效。请下调永续增长率或核对折现率假设。"}

    # ---- 逐年 FCFF ----
    rows = []
    revenue = base_revenue
    for i in range(n):
        revenue = revenue * (1 + growth_path[i])
        ebit = revenue * ebit_margin
        nopat = ebit * (1 - tax)
        da = revenue * da_pct
        capex = revenue * capex_pct
        delta_nwc = revenue * nwc_pct
        sbc = (revenue * safe_div(fin.latest(fin.sbc), base_revenue, 0.0)
               if asm.sbc_is_cash else 0.0)
        fcff = nopat + da - capex - delta_nwc - sbc
        rows.append({
            "year_index": i + 1,
            "growth": growth_path[i],
            "revenue": revenue,
            "ebit": ebit,
            "cash_tax": ebit * tax,
            "nopat": nopat,
            "da": da,
            "capex": capex,
            "delta_nwc": delta_nwc,
            "sbc": sbc,
            "fcff": fcff,
            # 期中折现（mid-year convention）：现金流在年内均匀发生，按 i+0.5 期折。
            # Excel 底稿用的是同一口径，两边必须一致，否则重算值对不上报告值。
            "discount_factor": 1 / (1 + wacc) ** (i + 0.5),
        })

    for row in rows:
        row["pv_fcff"] = row["fcff"] * row["discount_factor"]
    pv_explicit = sum(r["pv_fcff"] for r in rows)

    # ---- 终值：两种方法取中点 ----
    final = rows[-1]
    tv_gordon = final["fcff"] * (1 + g_terminal) / (wacc - g_terminal)

    # 退出倍数法：用可比公司中位 EV/EBITDA；没有就用 15x 并标注
    peer_ev_ebitda = [p.ev_ebitda for p in peers if p.ev_ebitda and 0 < p.ev_ebitda < 60]
    exit_multiple = median(peer_ev_ebitda) if peer_ev_ebitda else 15.0
    exit_source = "同业中位 EV/EBITDA" if peer_ev_ebitda else "缺同业数据，兜底 15x"
    ebitda_final = final["ebit"] + final["da"]
    tv_exit = ebitda_final * exit_multiple

    tv_base = 0.5 * (tv_gordon + tv_exit)
    divergence = abs(tv_gordon - tv_exit) / tv_base if tv_base else 0
    if divergence > 0.30:
        # 偏离的根源通常是 (WACC − g) 太小，让 Gordon 终值被放大
        spread = wacc - g_terminal
        warnings.append(
            f"终值两种算法偏离 {divergence:.0%}（Gordon {tv_gordon / 1e8:,.0f} 亿 vs "
            f"退出倍数 {tv_exit / 1e8:,.0f} 亿），已取中点。"
            + (f"根因多半是 WACC − g 只有 {spread:.2%}——分母太小会把 Gordon 终值放大。"
               f"建议复核折现率假设。" if spread < 0.04 else "建议回头核对假设。")
        )

    pv_tv = tv_base / (1 + wacc) ** n
    ev = pv_explicit + pv_tv
    tv_ratio = safe_div(pv_tv, ev, 0.0)
    if tv_ratio > 0.85:
        warnings.append(f"终值占企业价值 {tv_ratio:.0%}，超过 85%——这个模型实质上是在押倍数扩张。")
    elif tv_ratio < 0.45:
        warnings.append(f"终值占企业价值 {tv_ratio:.0%}，低于 45%——请确认预测期是否过长。")

    # ---- 桥接到股权价值 ----
    cash = fin.cash or 0.0
    debt = fin.total_debt or 0.0
    minority = fin.minority_interest or 0.0
    preferred = fin.preferred_stock or 0.0
    equity_value = ev + cash - debt - minority - preferred
    per_share = safe_div(equity_value, fin.shares_outstanding)

    # ---- 市场隐含折现率：反解出「让 DCF 等于当前市值」的 WACC ----
    # 这是最有用的诊断：如果算出来的 WACC 远低于市场隐含值，说明折现率假设太激进。
    implied_wacc = None
    if _solve_implied and fin.market_cap and fin.shares_outstanding:
        target_equity = fin.market_cap
        lo, hi = max(g_terminal + 0.005, 0.01), 0.60
        for _ in range(60):
            mid = (lo + hi) / 2
            sub = Assumptions.from_dict(asm.to_dict())
            block = compute_wacc(fin, sub, market)
            # 用 beta 反解把 WACC 拉到 mid
            if block["erp"] and block["equity_ratio"]:
                sub.beta = block["beta"] + (mid - block["wacc"]) / (block["erp"] * block["equity_ratio"])
            probe = build_dcf(fin, sub, market, peers, _solve_implied=False)
            if not probe.get("ok"):
                lo = mid
                continue
            if probe["equity_value"] > target_equity:
                lo = mid     # 折现率太低 → 估值太高 → 往上调
            else:
                hi = mid
            implied_wacc = mid
        implied_wacc = round((lo + hi) / 2, 6)

    # 诊断：算出来的折现率与市场隐含的差多少
    if implied_wacc and abs(implied_wacc - wacc) > 0.015:
        direction = "低于" if wacc < implied_wacc else "高于"
        warnings.append(
            f"算出的 WACC（{wacc:.2%}）{direction}市场隐含折现率（{implied_wacc:.2%}）"
            f"{abs(implied_wacc - wacc) * 10000:.0f}bp。"
            + ("折现率偏低会让 DCF 结果系统性高于市价——"
               "通常是无风险利率处在历史低位、Beta 偏低，或 ERP 取值偏小。"
               "建议把市场隐含折现率作为交叉验证，并在交付时说明这一分歧。"
               if wacc < implied_wacc else
               "折现率偏高会让 DCF 结果系统性低于市价，请核对是否过度保守。")
        )

    return {
        "ok": True,
        "method": "dcf",
        "implied_wacc": implied_wacc,
        "forecast_years": n,
        "revenue_growth_y1": y1,
        "revenue_growth_y1_source": y1_source,
        "hist_cagr": hist_cagr,
        "terminal_growth": g_terminal,
        "terminal_growth_cap": cap,
        "ebit_margin": ebit_margin,
        "ebit_margin_source": ebit_margin_src,
        "da_pct": da_pct, "da_pct_source": da_pct_src,
        "capex_pct": capex_pct, "capex_pct_source": capex_pct_src,
        "nwc_pct": nwc_pct, "nwc_pct_source": nwc_pct_src,
        "wacc_block": wacc_block,
        "wacc": wacc,
        "rows": rows,
        "pv_explicit": pv_explicit,
        "tv_gordon": tv_gordon,
        "tv_exit": tv_exit,
        "exit_multiple": exit_multiple,
        "exit_multiple_source": exit_source,
        "tv_base": tv_base,
        "tv_divergence": divergence,
        "pv_terminal": pv_tv,
        "enterprise_value": ev,
        "tv_ratio": tv_ratio,
        "cash": cash, "debt": debt, "minority_interest": minority,
        "preferred_stock": preferred,
        "equity_value": equity_value,
        "per_share": per_share,
        "warnings": warnings,
    }


# ======================================================================
# 相对估值
# ======================================================================


MULTIPLE_LABELS = {
    "pe": "市盈率 PE",
    "pe_forward": "预期市盈率",
    "pb": "市净率 PB",
    "ps": "市销率 PS",
    "ev_revenue": "EV/营业收入",
    "ev_ebitda": "EV/EBITDA",
    "ev_ebit": "EV/EBIT",
    "peg": "PEG",
}


def build_relative(fin: Financials, peers: list[Peer], asm: Assumptions,
                   multiples: list[str]) -> dict:
    """同业中位倍数 → 隐含股权价值。"""
    if not peers:
        return {"ok": False, "error": "没有可比公司，无法做相对估值"}

    warnings: list[str] = []
    metrics = {
        "revenue": fin.latest(fin.revenue),
        "net_income": fin.latest(fin.net_income),
        "ebit": fin.latest(fin.ebit),
        "ebitda": ((fin.latest(fin.ebit) or 0) + (fin.latest(fin.da) or 0)) or None,
        "equity": fin.total_equity,
    }
    net_debt = fin.net_debt()

    def peer_median(attr: str) -> tuple[float | None, list[float]]:
        vals = [getattr(p, attr) for p in peers if getattr(p, attr) is not None and getattr(p, attr) > 0]
        # 剔除明显离群（PE>100 或 EV/Rev>50），除非全部如此
        trimmed = [v for v in vals if v <= (100 if "pe" in attr else 50)]
        use = trimmed or vals
        return (median(use) if use else None), use

    results = []
    for key in multiples:
        med, samples = peer_median(key)
        if med is None:
            warnings.append(f"{MULTIPLE_LABELS.get(key, key)} 同业无有效数据，已跳过。")
            continue

        # 目标与同业的差异调整
        adjust = (asm.multiple_adjustment or {}).get(key, 0.0)
        adjusted = med * (1 + adjust)

        implied_equity = None
        basis = ""
        if key in ("pe", "pe_forward", "peg"):
            base = metrics["net_income"]
            if base and base > 0:
                implied_equity = adjusted * base
                basis = "净利润"
            else:
                warnings.append(f"{MULTIPLE_LABELS.get(key, key)}：标的净利润为负或缺失，已跳过。")
                continue
        elif key == "pb":
            if metrics["equity"] and metrics["equity"] > 0:
                implied_equity = adjusted * metrics["equity"]
                basis = "净资产"
            else:
                warnings.append("市净率：标的净资产为负或缺失，已跳过。")
                continue
        elif key == "ps":
            if metrics["revenue"]:
                implied_equity = adjusted * metrics["revenue"]
                basis = "营业收入"
            else:
                continue
        elif key in ("ev_revenue", "ev_ebitda", "ev_ebit"):
            metric_key = {"ev_revenue": "revenue", "ev_ebitda": "ebitda", "ev_ebit": "ebit"}[key]
            base = metrics[metric_key]
            if base and base > 0:
                implied_ev = adjusted * base
                implied_equity = implied_ev - net_debt
                basis = {"revenue": "营业收入", "ebitda": "EBITDA", "ebit": "EBIT"}[metric_key]
            else:
                warnings.append(f"{MULTIPLE_LABELS.get(key, key)}：标的对应指标为负或缺失，已跳过。")
                continue

        if implied_equity is None:
            continue

        results.append({
            "multiple": key,
            "label": MULTIPLE_LABELS.get(key, key),
            "peer_median": med,
            "adjustment": adjust,
            "applied_multiple": adjusted,
            "metric_basis": basis,
            "metric_value": metrics.get({"pe": "net_income", "pb": "equity", "ps": "revenue",
                                         "ev_revenue": "revenue", "ev_ebitda": "ebitda",
                                         "ev_ebit": "ebit"}.get(key, "revenue")),
            "net_debt_deducted": net_debt if key.startswith("ev_") else 0.0,
            "implied_equity_value": implied_equity,
            "implied_per_share": safe_div(implied_equity, fin.shares_outstanding),
            "sample_count": len(samples),
        })

    if not results:
        return {"ok": False, "error": "所有选用倍数都无有效数据", "warnings": warnings}

    equities = [r["implied_equity_value"] for r in results]
    per_shares = [r["implied_per_share"] for r in results if r["implied_per_share"] is not None]

    return {
        "ok": True,
        "method": "relative",
        "peers_used": len(peers),
        # 可比公司明细：Excel 的「相对估值」表靠它渲染倍数表。
        # 之前这张表读的是 result.meta.peers_detail，而全项目没人生产过那个字段，
        # 于是 5 家可比公司明明算出来了，表里却写着「未提供可比公司」。
        "peers_detail": [p.to_dict() for p in peers],
        "results": results,
        "implied_equity_value": median(equities),
        "implied_per_share": median(per_shares) if per_shares else None,
        "range_low": min(equities),
        "range_high": max(equities),
        "warnings": warnings,
    }


# ======================================================================
# 分部估值 SOTP
# ======================================================================


def build_sotp(fin: Financials, segments, assumptions: Assumptions) -> dict:
    """分部估值。A 股免费源拿不到分部数据，需使用者手工提供。"""
    if not segments:
        return {"ok": False, "skipped": True,
                "reason": "没有提供分部数据，跳过 SOTP。"}

    warnings = []
    rows = []
    total_ev = 0.0
    for seg in segments:
        if seg.value is None or seg.multiple is None:
            warnings.append(f"分部「{seg.name}」缺指标值或倍数，已跳过。")
            continue
        seg_ev = seg.value * seg.multiple
        total_ev += seg_ev
        rows.append({
            "name": seg.name,
            "metric": seg.metric,
            "value": seg.value,
            "multiple": seg.multiple,
            "segment_ev": seg_ev,
            "peers": seg.peer_names,
            "note": seg.note,
        })

    if not rows:
        return {"ok": False, "error": "没有可用的分部分部数据"}

    # 总部费用：未知时按收入的 2–5% 折算，这里取 3%，并按 8 倍资本化
    corporate_cost = 0.0
    revenue = fin.latest(fin.revenue)
    if revenue:
        corporate_cost = revenue * 0.03 * 8
        warnings.append("未提供总部费用，已按「营业收入的 3% × 8 倍」估算并从分部价值中扣除。")

    net_debt = fin.net_debt()
    equity = (total_ev - corporate_cost - (fin.minority_interest or 0)
              - (fin.preferred_stock or 0) - net_debt + (fin.cash or 0))
    per_share = safe_div(equity, fin.shares_outstanding)

    # 集团折价
    discount = None
    if fin.price and per_share:
        discount = (per_share - fin.price) / per_share

    return {
        "ok": True,
        "method": "sotp",
        "rows": rows,
        "segment_ev_total": total_ev,
        "corporate_cost": corporate_cost,
        "net_debt": net_debt,
        "equity_value": equity,
        "per_share": per_share,
        "conglomerate_discount": discount,
        "warnings": warnings,
    }
