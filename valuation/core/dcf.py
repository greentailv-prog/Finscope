"""DCF / FCFF 引擎（v3.1）。
默认独立 CAPM WACC 和 Gordon 永续终值；市场隐含 WACC 仅作校验。
没有真实退出倍数不得机械混合；过高终值占比、缺关键现金流数据需复核。
现金、债务、股本缺失或股权价值非正，只保留诊断，不输出正式目标价。
"""
from __future__ import annotations

from statistics import median

from . import defaults
from .metrics import clamp, safe_div
from .models import Assumptions, Financials, Peer


def _peer_exit_multiple(peers: list[Peer]) -> tuple[float, str]:
    vals = [p.ev_ebitda for p in (peers or []) if p.ev_ebitda and 0 < p.ev_ebitda < 60]
    if vals:
        return median(vals), f"同业中位 EV/EBITDA（{len(vals)} 家）"
    return None, "无有效同业 EV/EBITDA，退出倍数不可用"


def _core(fin: Financials, asm: Assumptions, wacc: float, g: float,
          terminal_method: str = "gordon",
          exit_multiple: float | None = None) -> dict | None:
    """给定 WACC 与 g，算完整 DCF。"""
    base_revenue = fin.latest(fin.revenue)
    if base_revenue is None:
        return None
    n = int(asm.forecast_years or 5)
    path = list(asm.revenue_growth_path or [])
    if len(path) != n:
        path = [asm.revenue_growth_y1 + (g - asm.revenue_growth_y1) * i / max(n - 1, 1)
                for i in range(n)]
    if wacc <= g:
        return None

    tax = asm.tax_rate
    ebit_margin = asm.ebit_margin
    da_pct = asm.da_pct_revenue
    capex_pct = asm.capex_pct_revenue
    nwc_pct = asm.nwc_pct_revenue

    driver_rows = getattr(asm, "_operating_driver_rows", None)
    if driver_rows is not None:
        if len(driver_rows) != n:
            return None
        rows = []
        for i, r in enumerate(driver_rows):
            df = 1 / (1 + wacc) ** (i + 0.5)
            v = dict(r)
            v.update(discount_factor=df, pv_fcff=r["fcff"] * df)
            rows.append(v)
    else:
        rows = []
        revenue = base_revenue
        base_year = fin.years[-1] if fin.years else None
        for i in range(n):
            previous_revenue = revenue
            revenue = revenue * (1 + path[i])
            ebit = revenue * ebit_margin
            cash_tax = max(0.0, ebit) * tax  # EBIT为负不得形成当期“负现金税”
            nopat = ebit - cash_tax
            da = revenue * da_pct
            capex = revenue * capex_pct
            if asm.nwc_forecast_basis == "delta_revenue":
                if asm.nwc_investment_ratio is None:
                    return None  # 禁止将 ΔNWC/Revenue 误作 ΔNWC/ΔRevenue
                delta_nwc = (revenue - previous_revenue) * asm.nwc_investment_ratio
            elif asm.nwc_forecast_basis == "revenue":
                delta_nwc = revenue * nwc_pct
            else:
                return None
            fcff = nopat + da - capex - delta_nwc
            df = 1 / (1 + wacc) ** (i + 0.5)   # 期中折现
            rows.append({
                "year_index": i + 1,
                "year": (base_year + i + 1) if base_year else f"Y{i + 1}",
                "growth": path[i],
                "revenue": revenue,
                "ebit": ebit,
                "ebit_margin": safe_div(ebit, revenue),
                "cash_tax": cash_tax,
                "nopat": nopat,
                "da": da,
                "da_pct": da_pct,
                "capex": capex,
                "capex_pct": capex_pct,
                "delta_nwc": delta_nwc,
                "nwc_pct": nwc_pct,
                "fcff": fcff,
                "discount_factor": df,
                "pv_fcff": fcff * df,
            })

    pv_explicit = sum(r["pv_fcff"] for r in rows)
    final = rows[-1]
    ebitda_final = final["ebit"] + final["da"]

    tv_gordon = final["fcff"] * (1 + g) / (wacc - g)
    tv_exit = (ebitda_final * exit_multiple if exit_multiple is not None and ebitda_final > 0
               else None)
    roic = asm.terminal_roic or max(0.10, wacc + 0.02)
    roic = max(roic, g + 0.005)
    tv_roic = final["nopat"] * (1 + g) * (1 - g / roic) / (wacc - g)

    method = (terminal_method or "blend").lower()
    if method == "gordon":
        tv_base = tv_gordon
    elif method == "exit":
        tv_base = tv_exit
    elif method == "roic":
        tv_base = tv_roic
    else:  # 仅在有真正同业且差异可控时允许混合终值
        if tv_exit is None or tv_gordon <= 0:
            return None
        deviation = abs(tv_gordon - tv_exit) / max(abs(tv_gordon), abs(tv_exit))
        if deviation > 0.30:
            return None
        tv_base = 0.5 * (tv_gordon + tv_exit)
    if tv_base is None or tv_base <= 0:
        return None

    pv_tv = tv_base / (1 + wacc) ** n
    ev = pv_explicit + pv_tv
    # 不把未知净债务、少数股权、总股本误当为 0；优先由上游核验后输入。
    if fin.cash is None or fin.total_debt is None or not fin.shares_outstanding:
        return None
    cash, debt = fin.cash, fin.total_debt
    minority, preferred = fin.minority_interest or 0.0, fin.preferred_stock or 0.0
    equity = ev + cash - debt - minority - preferred
    per_share = safe_div(equity, fin.shares_outstanding)
    tv_ratio = safe_div(pv_tv, ev)
    divergence = (safe_div(abs(tv_gordon - tv_exit), tv_base)
                  if tv_exit is not None else None)

    return {
        "rows": rows,
        "pv_explicit": pv_explicit,
        "tv_gordon": tv_gordon,
        "tv_exit": tv_exit,
        "tv_roic": tv_roic,
        "exit_multiple": exit_multiple,
        "exit_multiple_source": "",
        "tv_base": tv_base,
        "tv_divergence": divergence,
        "pv_terminal": pv_tv,
        "enterprise_value": ev,
        "tv_ratio": tv_ratio,
        "equity_value": equity,
        "per_share": per_share,
        "terminal_roic": roic,
    }


def _solve_implied(fin: Financials, asm: Assumptions, g: float,
                   terminal_method: str, exit_multiple: float | None = None) -> float | None:
    """反解「让 DCF 每股价值 = 当前股价」的 WACC。"""
    if not (fin.market_cap and fin.shares_outstanding and fin.price):
        return None
    target = fin.market_cap
    lo = max(g + 0.005, 0.01)
    hi = 0.60
    best = None
    for _ in range(70):
        mid = (lo + hi) / 2
        probe = _core(fin, asm, mid, g, terminal_method, exit_multiple=exit_multiple)
        if not probe or probe.get("equity_value") is None:
            lo = mid
            continue
        if probe["equity_value"] > target:
            lo = mid       # 折现率太低 → 估值太高 → 提高折现率
        else:
            hi = mid
        best = mid
    return round((lo + hi) / 2, 6) if best is not None else None


def build_dcf(fin: Financials, asm: Assumptions, market: str = "A",
              peers: list[Peer] | None = None,
              wacc_override: float | None = None,
              terminal_growth_override: float | None = None,
              solve_implied: bool = True) -> dict:
    peers = peers or []
    warnings: list[str] = []
    mkt = defaults.market_defaults(market)

    base_revenue = fin.latest(fin.revenue)
    if base_revenue is None or base_revenue <= 0:
        return {"ok": False, "error": "缺少有效营业收入历史数据，无法建立 DCF。"}
    if fin.cash is None or fin.total_debt is None or not fin.shares_outstanding:
        return {"ok": False, "status": "blocked", "error": "缺少净债务或总股本，无法可靠地将 EV 转换为每股股权价值。",
                "warnings": ["现金、计息债务和总股本需要统一报告期及单位，不把缺失值设成0。"]}

    g = terminal_growth_override if terminal_growth_override is not None else asm.terminal_growth
    cap = mkt["terminal_growth_cap"]
    if g is None:
        g = mkt["default_terminal_growth"]
    if g > cap:
        warnings.append(f"永续增长率 {g:.2%} 超过 {market} 市场可辩护上限 {cap:.1%}，已按上限处理。")
        g = cap

    wacc_capm = getattr(asm, "_wacc_capm", None)
    if wacc_capm is None:
        wacc_capm = getattr(asm, "_wacc_capm", 0.09)
        if asm.risk_free is not None and asm.erp is not None and asm.beta is not None:
            ke = asm.risk_free + asm.beta * asm.erp + (asm.size_premium or 0)
            d = asm.target_debt_ratio or 0
            wacc_capm = (1 - d) * ke + d * (asm.cost_of_debt or 0.04) * (1 - (asm.tax_rate or 0.21))

    # 退出倍数只算一次：隐含 WACC 反解和正式 DCF 必须用同一个终值口径，
    # 否则反解出来的折现率会系统性偏高（旧版就是这样把 000333 的隐含 WACC
    # 推到 13% 的）。
    exit_multiple, exit_source = _peer_exit_multiple(peers)

    # ---- 市场隐含 WACC ----
    implied_wacc = (_solve_implied(fin, asm, g, asm.terminal_method,
                                   exit_multiple=exit_multiple)
                    if solve_implied else None)

    # ---- 选择实际使用的 WACC ----
    wacc_mode = (asm.wacc_mode or "capm").lower()
    recon_rule = defaults.wacc_rules()
    reconciliation = None
    if wacc_override is not None:
        wacc_used = wacc_override
        wacc_source = "使用者手工指定 WACC"
    elif wacc_mode == "manual" and asm.wacc_override is not None:
        wacc_used = asm.wacc_override
        wacc_source = "使用者手工指定 WACC"
    elif wacc_mode == "capm":
        wacc_used = wacc_capm
        wacc_source = "CAPM 计算值（未做市场校准）"
    else:
        wacc_used = wacc_capm
        wacc_source = "CAPM 计算值"
        if implied_wacc is not None and recon_rule.get("enabled_by_default", True):
            gap = implied_wacc - wacc_capm
            if abs(gap) > recon_rule.get("trigger_gap", 0.015):
                adjust = clamp(gap * recon_rule.get("move_fraction", 0.60),
                               -recon_rule.get("max_adjustment", 0.04),
                               recon_rule.get("max_adjustment", 0.04))
                wacc_used = wacc_capm + adjust
                reconciliation = {
                    "capm_wacc": wacc_capm,
                    "implied_wacc": implied_wacc,
                    "gap": gap,
                    "adjustment": adjust,
                    "applied": True,
                    "rule": (f"CAPM 与市场隐含折现率相差 {abs(gap) * 10000:.0f}bp，"
                             f"按规则向市场隐含值靠拢 {abs(adjust) * 10000:.0f}bp"),
                }
                wacc_source = (f"CAPM {wacc_capm:.2%} 与市场隐含 {implied_wacc:.2%} 相差 "
                               f"{abs(gap) * 10000:.0f}bp，规则校准至 {wacc_used:.2%}")
    wacc_used = clamp(wacc_used, recon_rule.get("min_wacc", 0.03), recon_rule.get("max_wacc", 0.25))

    # ---- 闸门：WACC 必须高于 g ----
    if wacc_used <= g + 0.002:
        return {"ok": False, "status": "blocked",
                "error": f"WACC（{wacc_used:.2%}）与永续增长率（{g:.2%}）差距不足20bp，终值公式不稳健。",
                "warnings": ["不自动改变用户的g，请重新设定现金流永续阶段与折现率。"]}

    core = _core(fin, asm, wacc_used, g, asm.terminal_method, exit_multiple=exit_multiple)
    if core is None:
        return {"ok": False, "status": "blocked",
                "error": "DCF 终值/基础数据无法通过校验：可能是 WACC≤g、终值为负、同业倍数缺失、混合终值差异过大或净债务缺失。",
                "warnings": ["请复核 g、终值方式、同业倍数和财务桥；不自动写入目标价。"]}
    if core["equity_value"] <= 0 or core["per_share"] is None or core["per_share"] <= 0:
        return {"ok": False, "status": "blocked",
                "error": "DCF 股权价值≤0，不生成负的每股目标价；需复核净负债、增长和再投资假设。",
                "diagnostic_values": {"enterprise_value": core["enterprise_value"],
                                      "equity_value": core["equity_value"],
                                      "cash": fin.cash, "debt": fin.total_debt},
                "warnings": ["保留负股权价值作为数学诊断，但禁止进入综合估值。"]}
    core["exit_multiple"] = exit_multiple
    core["exit_multiple_source"] = exit_source

    # ---- 诊断 ----
    if asm.nwc_forecast_basis == "revenue" and (asm.nwc_pct_revenue or 0) > 0.08:
        warnings.append("ΔNWC 按收入固定费率预测且超过8%，扩张期可能高估现金投入，建议按净营运资本余额与周转天数重建。")
    if core["tv_ratio"] is not None:
        if core["tv_ratio"] > 0.85:
            warnings.append(f"终值占企业价值 {core['tv_ratio']:.0%}，超过 85%——模型实质上是在押远期倍数/永续假设，"
                            "结论对 WACC 与 g 高度敏感。")
        elif core["tv_ratio"] < 0.45:
            warnings.append(f"终值占企业价值 {core['tv_ratio']:.0%}，低于 45%——请确认预测期是否过长或现金流是否偏低。")
    if core["tv_divergence"] is not None and core["tv_divergence"] > 0.30:
        warnings.append(
            f"终值两种算法偏离 {core['tv_divergence']:.0%}（Gordon {core['tv_gordon'] / 1e8:,.0f} 亿元 vs "
            f"退出倍数 {core['tv_exit'] / 1e8:,.0f} 亿元），仅作交叉诊断；当前终值使用独立选择的方法，未取中点。"
            f"根因多半是 WACC−g 只有 {wacc_used - g:.2%}，分母过小会放大 Gordon 终值。"
        )
    if implied_wacc is not None and abs(implied_wacc - wacc_capm) > 0.015:
        direction = "低于" if wacc_capm < implied_wacc else "高于"
        warnings.append(
            f"CAPM 算出的 WACC（{wacc_capm:.2%}）{direction}市场隐含折现率（{implied_wacc:.2%}）"
            f"{abs(implied_wacc - wacc_capm) * 10000:.0f}bp。"
            + ("CAPM 折现率偏低会让 DCF 系统性高于市价；本次已按规则校准。" if wacc_capm < implied_wacc
               else "CAPM 折现率偏高会让 DCF 系统性低于市价，请核对是否过度保守。")
        )

    wacc_block = {
        "risk_free": asm.risk_free,
        "risk_free_source": getattr(asm, "_risk_free_source", ""),
        "erp": asm.erp,
        "erp_source": getattr(asm, "_erp_source", ""),
        "beta": asm.beta,
        "beta_source": getattr(asm, "_beta_source", ""),
        "size_premium": asm.size_premium,
        "cost_of_equity": getattr(asm, "_ke", None),
        "cost_of_debt": asm.cost_of_debt,
        "cost_of_debt_source": getattr(asm, "_kd_source", ""),
        "tax_rate": asm.tax_rate,
        "equity_ratio": 1 - (asm.target_debt_ratio or 0.0),
        "debt_ratio": asm.target_debt_ratio or 0.0,
        "capital_source": getattr(asm, "_capital_source", ""),
        "wacc_capm": wacc_capm,
        "wacc": wacc_used,
    }

    return {
        "ok": True,
        "method": "dcf",
        "status": "ok",
        "wacc": wacc_used,
        "wacc_capm": wacc_capm,
        "wacc_source": wacc_source,
        "wacc_mode": wacc_mode,
        "wacc_reconciliation": reconciliation,
        "implied_wacc": implied_wacc,
        "wacc_block": wacc_block,
        "terminal_growth": g,
        "terminal_growth_cap": cap,
        "terminal_method": asm.terminal_method,
        "terminal_roic": asm.terminal_roic,
        "forecast_years": asm.forecast_years,
        "base_revenue": base_revenue,
        "base_year": fin.years[-1] if fin.years else None,
        "revenue_growth_y1": asm.revenue_growth_y1,
        "revenue_growth_path": asm.revenue_growth_path,
        "ebit_margin": asm.ebit_margin,
        "da_pct": asm.da_pct_revenue,
        "capex_pct": asm.capex_pct_revenue,
        "nwc_pct": asm.nwc_pct_revenue,
        "nwc_forecast_basis": asm.nwc_forecast_basis,
        "nwc_investment_ratio": asm.nwc_investment_ratio,
        "tax_rate": asm.tax_rate,
        "rows": core["rows"],
        "forecast": core["rows"],
        "pv_explicit": core["pv_explicit"],
        "tv_gordon": core["tv_gordon"],
        "tv_exit": core["tv_exit"],
        "tv_roic": core["tv_roic"],
        "exit_multiple": core["exit_multiple"],
        "exit_multiple_source": core["exit_multiple_source"],
        "tv_base": core["tv_base"],
        "tv_divergence": core["tv_divergence"],
        "pv_terminal": core["pv_terminal"],
        "enterprise_value": core["enterprise_value"],
        "tv_ratio": core["tv_ratio"],
        "cash": fin.cash or 0.0,
        "debt": fin.total_debt or 0.0,
        "minority_interest": fin.minority_interest or 0.0,
        "preferred_stock": fin.preferred_stock or 0.0,
        "equity_value": core["equity_value"],
        "per_share": core["per_share"],
        "warnings": warnings,
        "review_required": bool(getattr(asm, "_driver_review_required", False) or
                                (core["tv_ratio"] is not None and core["tv_ratio"] > 0.85) or
                                (core["tv_divergence"] is not None and core["tv_divergence"] > 0.50) or
                                (fin.latest(fin.da) is None or fin.latest(fin.capex) is None)),
        "diagnostics": {
            "tv_ratio": core["tv_ratio"],
            "tv_divergence": core["tv_divergence"],
            "wacc_gap_bp": round(abs(implied_wacc - wacc_capm) * 10000, 0) if implied_wacc else None,
            "wacc_minus_g": wacc_used - g,
            "terminal_roic": core["terminal_roic"],
        },
    }
