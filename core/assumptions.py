"""假设规则层：把历史财务 + 用户覆盖 + 市场参数，解析成一套可执行、可披露的假设。

核心原则（与 RULES.md 一致）：
  1. 用中位数，不用最近值；
  2. 用户给了就尊重用户，但记录「手工指定」；
  3. 数据缺失时按规则估算，并明确标注「估算」与置信度，不假装是原始数据；
  4. 任何假设都进台账，展示层只引用台账。
"""
from __future__ import annotations

from statistics import median

from . import defaults
from .metrics import (
    cagr, clamp, median_last_n, safe_div, series_growth, volatility,
)
from .models import Assumptions, Company, Financials


def _entry(name, value, unit, source_type, source, confidence, overridable=True, note=""):
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "source_type": source_type,
        "source": source,
        "confidence": confidence,
        "overridable": overridable,
        "note": note,
    }


def _growth_confidence(series: list[float | None]) -> str:
    vals = [v for v in (series or []) if v is not None]
    if len(vals) < 3:
        return "低"
    vol = volatility(series_growth(vals))
    if vol is None:
        return "中"
    if vol < 0.25:
        return "高"
    if vol < 0.60:
        return "中"
    return "低"


def _ratio_series(fin: Financials, key: str, denominator: str = "revenue",
                  absolute: bool = False) -> list[float | None]:
    num = getattr(fin, key, None) or []
    den = getattr(fin, denominator, None) or []
    out = []
    for i, value in enumerate(num):
        if i >= len(den):
            break
        ratio = safe_div(value, den[i])
        if ratio is not None:
            out.append(abs(ratio) if absolute else ratio)
    return out


def historical_growth(fin: Financials) -> dict:
    rev = [v for v in (fin.revenue or []) if v is not None]
    ni = [v for v in (fin.net_income or []) if v is not None]
    out = {"cagr_3y": None, "cagr_5y": None, "latest_yoy": None,
           "ni_cagr_3y": None, "ni_latest_yoy": None, "years": len(rev)}
    if len(rev) >= 2:
        out["latest_yoy"] = safe_div(rev[-1], rev[-2]) - 1 if rev[-2] else None
        periods = min(3, len(rev) - 1)
        out["cagr_3y"] = cagr(rev[-periods - 1], rev[-1], periods)
        periods5 = min(5, len(rev) - 1)
        out["cagr_5y"] = cagr(rev[-periods5 - 1], rev[-1], periods5)
    if len(ni) >= 2 and ni[-2]:
        out["ni_latest_yoy"] = ni[-1] / ni[-2] - 1
        periods = min(3, len(ni) - 1)
        out["ni_cagr_3y"] = cagr(ni[-periods - 1], ni[-1], periods) if ni[-periods - 1] and ni[-periods - 1] > 0 else None
    return out


def _blend_growth(hist: dict) -> tuple[float | None, str]:
    parts = []
    if hist.get("cagr_3y") is not None:
        parts.append((hist["cagr_3y"], 0.50, "近 3 年 CAGR"))
    if hist.get("cagr_5y") is not None:
        parts.append((hist["cagr_5y"], 0.30, "近 5 年 CAGR"))
    if hist.get("latest_yoy") is not None:
        parts.append((hist["latest_yoy"], 0.20, "最近一年同比"))
    if not parts:
        return None, "历史收入不足"
    total_w = sum(w for _, w, _ in parts)
    value = sum(v * w for v, w, _ in parts) / total_w
    detail = " + ".join(f"{label} {v:.1%}×{w:.0%}" for v, w, label in parts)
    return value, detail


def _effective_beta(fin: Financials, user: Assumptions, industry: str, business: str) -> tuple[float, str, dict]:
    anchor = defaults.sector_anchor(industry, business) or {}
    sector_beta = float(anchor.get("beta") or 1.0)
    raw = user.beta if user.beta is not None else fin.beta
    detail = {"raw": raw, "sector": sector_beta, "anchor": anchor.get("label", "")}

    if user.beta is not None:
        return clamp(float(user.beta), 0.2, 2.5), "手工指定 Beta", detail
    if raw is None or raw <= 0 or raw > 3.0:
        return sector_beta, f"数据源 Beta 缺失/异常，使用行业锚点 {anchor.get('label') or '通用'} Beta {sector_beta:.2f}", detail

    mode = (user.beta_mode or "blume").lower()
    if mode == "raw":
        beta, src = float(raw), "数据源原始 Beta（未做调整）"
    elif mode == "sector":
        beta, src = sector_beta, f"行业锚点 Beta（{anchor.get('label') or '通用'}）"
    else:  # blume
        beta = 0.67 * float(raw) + 0.33 * 1.0
        src = f"Blume 调整：0.67×原始 Beta {raw:.2f} + 0.33×1.0"
    # 防止回归 Beta 异常偏低/偏高：与行业锚点偏离过大时收窄到行业锚点附近
    if sector_beta and (beta < sector_beta * 0.60 or beta > sector_beta * 1.60):
        adjusted = clamp(beta, sector_beta * 0.70, sector_beta * 1.40)
        src += f"；与行业锚点 {sector_beta:.2f} 偏离过大，收窄至 {adjusted:.2f}"
        beta = adjusted
    return clamp(beta, 0.2, 2.5), src, detail


def _cost_of_debt(fin: Financials, user: Assumptions, market: str) -> tuple[float, str, str]:
    mkt = defaults.market_defaults(market)
    if user.cost_of_debt is not None:
        return clamp(float(user.cost_of_debt), 0.005, 0.20), "手工指定税前债务成本", "手工指定"
    interest = fin.latest(fin.interest_expense)
    debt = fin.total_debt
    if interest is not None and debt and debt > 0:
        kd = interest / debt
        if 0.005 < kd < 0.20:
            return kd, f"利息费用 {interest / 1e8:,.1f} 亿元 ÷ 有息负债 {debt / 1e8:,.1f} 亿元", "报表推算"
    return mkt["cost_of_debt"], f"{market} 市场默认税前债务成本（LPR/信用利差口径）", "市场默认"


def _tax_rate(fin: Financials, user: Assumptions) -> tuple[float, str, str]:
    tc = defaults.tax_clamp()
    if user.tax_rate is not None:
        return clamp(float(user.tax_rate), 0.0, 0.40), "手工指定所得税率", "手工指定"
    rates = []
    for tax, pretax in zip(fin.tax_provision or [], fin.pretax_income or []):
        if tax is None or pretax in (None, 0):
            continue
        rate = tax / pretax
        if -0.5 < rate < 1.0:
            rates.append(rate)
    med = median(rates[-3:]) if rates else None
    if med is None:
        return tc["fallback"], "缺少利润总额/所得税，兜底 21%", "兜底"
    clipped = clamp(med, tc["low"], tc["high"])
    source = f"近三年有效税率中位数 {med:.1%}，夹在 {tc['low']:.0%}–{tc['high']:.0%}"
    return clipped, source, "报表推算"


def _margin_ratio(fin: Financials, key: str, denominator="revenue", absolute=False) -> float | None:
    return median_last_n(_ratio_series(fin, key, denominator, absolute), 3)


def resolve(fin: Financials, company: Company, user: Assumptions | None = None,
            market_rates: dict | None = None) -> tuple[Assumptions, list[dict], list[str]]:
    """返回 (有效假设, 假设台账, 提示)。"""
    user = user or Assumptions()
    market = company.market or "A"
    mkt = defaults.market_defaults(market)
    rates = market_rates or {}
    ledger: list[dict] = []
    warnings: list[str] = []

    # ---------------------------------------------------------------- 预测期
    n = int(user.forecast_years or 5)
    n = max(3, min(n, 10))
    if n != user.forecast_years:
        warnings.append(f"预测期已从 {user.forecast_years} 年调整为 {n} 年（允许 3–10 年）。")
    ledger.append(_entry("预测期", n, "年", "model", "标准 5 年显式预测期；可调 3–10 年", "中"))

    # ---------------------------------------------------------------- 收入增速
    hist = historical_growth(fin)
    base_revenue = fin.latest(fin.revenue)
    if base_revenue is None:
        raise ValueError("缺少营业收入历史数据，无法建立估值模型")

    if user.revenue_growth_y1 is not None:
        y1 = float(user.revenue_growth_y1)
        y1_source = "使用者指定"
        y1_type = "management"
        y1_conf = "中"
    else:
        y1, blend_detail = _blend_growth(hist)
        if y1 is None:
            y1, blend_detail = 0.05, "历史不足，兜底 5%"
            y1_type, y1_conf = "model", "低"
        else:
            y1_type = "history"
            y1_conf = _growth_confidence(fin.revenue)
        y1_source = f"规则合成：{blend_detail}"
    # 合理性约束：成熟公司不假设长期高速；周期底部不假设永久负增长
    raw_y1 = y1
    cap = 0.35 if (fin.market_cap or 0) < 2e10 else 0.25
    y1 = clamp(y1, -0.20, cap)
    if raw_y1 != y1:
        warnings.append(f"首年收入增速 {raw_y1:.1%} 超出合理区间，已按 {y1:.1%} 处理。")
    ledger.append(_entry("首年收入增速", y1, "小数", y1_type, y1_source, y1_conf,
                         note="按近 3/5 年 CAGR 与最近一年同比加权，并向永续增速线性衰减"))

    # ---------------------------------------------------------------- 永续增长
    cap_g = mkt["terminal_growth_cap"]
    g = user.terminal_growth if user.terminal_growth is not None else mkt["default_terminal_growth"]
    g_source = "使用者指定" if user.terminal_growth is not None else "市场长期名义 GDP 口径默认值"
    if g > cap_g:
        warnings.append(f"永续增长率 {g:.2%} 超过 {market} 市场可辩护上限 {cap_g:.1%}，已按上限处理。")
        g = cap_g
    g = max(g, -0.02)
    ledger.append(_entry("永续增长率 g", g, "小数", "industry" if user.terminal_growth is None else "management",
                         f"{g_source}；上限 {cap_g:.1%}（长期名义 GDP）", "中"))

    # ---------------------------------------------------------------- 利润率 / 费率
    ebit_margin = user.ebit_margin
    if ebit_margin is None:
        ebit_margin = _margin_ratio(fin, "ebit")
        if ebit_margin is None:
            # 用净利率 + 税率反推
            net_margin = _margin_ratio(fin, "net_income")
            if net_margin is not None:
                tax_probe, _, _ = _tax_rate(fin, Assumptions())
                ebit_margin = net_margin / max(1 - tax_probe, 0.5)
                ebit_src = f"缺 EBIT，用净利率 {net_margin:.1%} ÷ (1−税率) 反推"
                ebit_conf = "低"
            else:
                ebit_margin, ebit_src, ebit_conf = 0.10, "缺 EBIT，兜底 10%", "低"
        else:
            ebit_src = "近三年 EBIT / 营业收入中位数"
            ebit_conf = "高" if (fin.ebit and len([v for v in fin.ebit[-3:] if v is not None]) >= 3) else "中"
        ebit_margin = clamp(ebit_margin, -0.30, 0.85)
    else:
        ebit_src, ebit_conf = "使用者指定", "中"
    ledger.append(_entry("EBIT 利润率", ebit_margin, "小数", "history" if user.ebit_margin is None else "management",
                         ebit_src, ebit_conf))

    da_pct = user.da_pct_revenue
    if da_pct is None:
        da_pct = _margin_ratio(fin, "da", absolute=True)
        if da_pct is None:
            da_pct, da_src, da_conf = 0.03, "缺折旧摊销，按收入 3% 估算", "低"
        else:
            da_src, da_conf = "近三年折旧摊销 / 营业收入中位数", "中"
    else:
        da_src, da_conf = "使用者指定", "中"
    da_pct = clamp(da_pct, 0.0, 0.40)
    ledger.append(_entry("折旧摊销 / 收入", da_pct, "小数", "history" if user.da_pct_revenue is None else "management",
                         da_src, da_conf))

    capex_pct = user.capex_pct_revenue
    if capex_pct is None:
        capex_pct = _margin_ratio(fin, "capex", absolute=True)
        if capex_pct is None:
            capex_pct = max(da_pct * 1.15, 0.03)
            capex_src, capex_conf = f"缺资本开支，按折旧摊销的 1.15 倍估算（{capex_pct:.1%}）", "低"
        else:
            capex_src, capex_conf = "近三年资本开支 / 营业收入中位数", "中"
    else:
        capex_src, capex_conf = "使用者指定", "中"
    capex_pct = clamp(capex_pct, 0.0, 0.50)
    ledger.append(_entry("资本开支 / 收入", capex_pct, "小数", "history" if user.capex_pct_revenue is None else "management",
                         capex_src, capex_conf))

    nwc_pct = user.nwc_pct_revenue
    if nwc_pct is None:
        nwc_pct = _margin_ratio(fin, "delta_nwc", absolute=False)
        if nwc_pct is None:
            nwc_pct, nwc_src, nwc_conf = 0.02, "缺营运资本变动，按收入 2% 估算", "低"
        else:
            nwc_src, nwc_conf = "近三年营运资本变动 / 营业收入中位数", "中"
    else:
        nwc_src, nwc_conf = "使用者指定", "中"
    nwc_pct = clamp(nwc_pct, -0.20, 0.30)
    ledger.append(_entry("营运资本变动 / 收入", nwc_pct, "小数", "history" if user.nwc_pct_revenue is None else "management",
                         nwc_src, nwc_conf))

    tax, tax_src, tax_type = _tax_rate(fin, user)
    ledger.append(_entry("所得税率", tax, "小数", "history" if user.tax_rate is None else "management",
                         tax_src, "高" if user.tax_rate is None else "中"))

    # ---------------------------------------------------------------- WACC
    rf = user.risk_free
    if rf is None:
        rf = rates.get("risk_free")
        rf_source = rates.get("risk_free_source") or f"{market} 市场默认"
    else:
        rf_source = "使用者指定"
    if rf is None:
        rf = mkt["risk_free"]
        rf_source = f"{market} 市场默认"
    rf = clamp(float(rf), 0.0, 0.15)
    ledger.append(_entry("无风险利率 rf", rf, "小数", "industry", rf_source, "高" if rates.get("risk_free") else "中"))

    erp = user.erp if user.erp is not None else (rates.get("erp") or mkt["erp"])
    erp_source = "使用者指定" if user.erp is not None else (rates.get("erp_source") or mkt["erp_source"])
    erp = clamp(float(erp), 0.02, 0.15)
    ledger.append(_entry("股权风险溢价 ERP", erp, "小数", "industry", erp_source, "中"))

    beta, beta_src, beta_detail = _effective_beta(fin, user, company.industry, company.business)
    ledger.append(_entry("Beta", beta, "倍", "model", beta_src, "中",
                         note=f"原始 Beta={beta_detail.get('raw')}，行业锚点={beta_detail.get('sector')}"))
    size_prem, size_src = (user.size_premium, "使用者指定") if user.size_premium is not None else defaults.size_premium(fin.market_cap)
    ke = rf + beta * erp + (size_prem or 0.0)
    ledger.append(_entry("股权成本 Ke", ke, "小数", "model", f"rf {rf:.2%} + β {beta:.2f} × ERP {erp:.2%} + 规模溢价 {size_prem:.2%}", "中"))

    kd, kd_src, kd_type = _cost_of_debt(fin, user, market)
    ledger.append(_entry("税前债务成本 Kd", kd, "小数", "history" if kd_type == "报表推算" else "industry", kd_src, "中"))
    ledger.append(_entry("所得税率（WACC 用）", tax, "小数", "history", tax_src, "高"))

    market_cap = fin.market_cap or safe_div(fin.price * fin.shares_outstanding if fin.price and fin.shares_outstanding else None, 1)
    debt = fin.total_debt or 0.0
    if user.target_debt_ratio is not None:
        d_ratio = clamp(float(user.target_debt_ratio), 0.0, 0.85)
        cap_src = "使用者指定目标资本结构"
    elif market_cap:
        d_ratio = clamp(debt / (market_cap + debt), 0.0, 0.85)
        cap_src = "当前市值口径：D/(E+D)，E=总市值"
    elif fin.total_equity:
        d_ratio = clamp(debt / (fin.total_equity + debt), 0.0, 0.85)
        cap_src = "市值缺失，用账面权益口径"
    else:
        d_ratio = clamp(debt / (debt + 1e12), 0.0, 0.85) if debt else 0.0
        cap_src = "市值与权益均缺失，按有息负债占比估算"
    e_ratio = 1 - d_ratio
    wacc_capm = e_ratio * ke + d_ratio * kd * (1 - tax)
    ledger.append(_entry("资本结构 D/(D+E)", d_ratio, "小数", "model", cap_src, "中"))
    ledger.append(_entry("WACC（CAPM 口径）", wacc_capm, "小数", "model",
                         f"{e_ratio:.1%}×Ke {ke:.2%} + {d_ratio:.1%}×Kd {kd:.2%}×(1−{tax:.1%})", "中"))

    # ---------------------------------------------------------------- 终值 ROIC
    terminal_roic = user.terminal_roic
    if terminal_roic is None:
        terminal_roic = max(0.10, wacc_capm + 0.02)
    terminal_roic = clamp(terminal_roic, max(g + 0.005, 0.02), 0.50)
    ledger.append(_entry("长期 ROIC（终值再投资率）", terminal_roic, "小数", "model",
                         f"再投资率 = g / ROIC = {g / terminal_roic:.1%}；默认不低于 WACC+2%", "中"))

    if user.sotp_corporate_cost is not None:
        ledger.append(_entry("SOTP 总部费用现值", user.sotp_corporate_cost, "元", "management",
                             "使用者确认：已含于分部利润时填0", "中"))

    # ---------------------------------------------------------------- 输出
    eff = Assumptions.from_dict(user.to_dict())
    eff.forecast_years = n
    eff.revenue_growth_y1 = y1
    eff.terminal_growth = g
    eff.terminal_roic = terminal_roic
    eff.ebit_margin = ebit_margin
    eff.da_pct_revenue = da_pct
    eff.capex_pct_revenue = capex_pct
    eff.nwc_pct_revenue = nwc_pct
    eff.tax_rate = tax
    eff.risk_free = rf
    eff.erp = erp
    eff.beta = beta
    eff.cost_of_debt = kd
    eff.size_premium = size_prem
    eff.target_debt_ratio = d_ratio
    if not eff.revenue_growth_path:
        eff.revenue_growth_path = [y1 + (g - y1) * i / (n - 1) for i in range(n)] if n > 1 else [y1]
    # 记录中间量，供输出层展示
    eff.__dict__["_wacc_capm"] = wacc_capm
    eff.__dict__["_ke"] = ke
    eff.__dict__["_risk_free_source"] = rf_source
    eff.__dict__["_erp_source"] = erp_source
    eff.__dict__["_beta_source"] = beta_src
    eff.__dict__["_kd_source"] = kd_src
    eff.__dict__["_capital_source"] = cap_src
    eff.__dict__["_hist_growth"] = hist
    return eff, ledger, warnings
