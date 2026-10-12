"""三法融合 + 敏感性矩阵 + 三情景。

这一步是 finance-skills 方法论里最有价值的部分：不单独给一个 DCF 结论，
而是把 DCF / 相对估值 / SOTP 加权成一个隐含股价，再给出区间与情景。
"""
from __future__ import annotations

from statistics import median

from . import methods
from .models import Assumptions, Financials, Peer, SotpSegment

DEFAULT_WEIGHTS = {"dcf": 0.5, "relative": 0.5}
DEFAULT_WEIGHTS_WITH_SOTP = {"dcf": 0.4, "relative": 0.3, "sotp": 0.3}


def _weights(asm: Assumptions, has_sotp: bool) -> tuple[dict, str]:
    if asm.weights:
        total = sum(asm.weights.values()) or 1.0
        return ({k: v / total for k, v in asm.weights.items()},
                "手工指定权重（已归一化）")
    if has_sotp:
        return DEFAULT_WEIGHTS_WITH_SOTP, "默认权重：多分部时 DCF 40% / 相对 30% / SOTP 30%"
    return DEFAULT_WEIGHTS, "默认权重：DCF 50% / 相对估值 50%"


def blend(dcf: dict, relative: dict, sotp: dict | None,
          asm: Assumptions, fin: Financials) -> dict:
    """把三种方法的隐含股价加权成一个值。"""
    weights, weight_source = _weights(asm, bool(sotp and sotp.get("ok")))

    parts = []
    if dcf.get("ok"):
        parts.append(("dcf", "DCF（收益法）", dcf.get("per_share"), weights.get("dcf", 0.0),
                      dcf.get("equity_value")))
    if relative.get("ok"):
        parts.append(("relative", "相对估值（市场法）", relative.get("implied_per_share"),
                      weights.get("relative", 0.0), relative.get("implied_equity_value")))
    if sotp and sotp.get("ok"):
        parts.append(("sotp", "分部估值（SOTP）", sotp.get("per_share"),
                      weights.get("sotp", 0.0), sotp.get("equity_value")))

    usable = [p for p in parts if p[2] is not None and p[3] > 0]
    if not usable:
        return {"ok": False, "error": "没有任何一种方法得出有效结果"}

    total_w = sum(p[3] for p in usable) or 1.0
    blended_price = sum(p[2] * p[3] for p in usable) / total_w
    blended_equity = sum((p[4] or 0) * p[3] for p in usable) / total_w

    price = fin.price
    upside = (blended_price / price - 1) if price else None

    # 找出最乐观 / 最悲观的方法
    ranked = sorted(usable, key=lambda p: p[2], reverse=True)
    most_bullish = ranked[0][1] if len(ranked) > 1 else None
    most_bearish = ranked[-1][1] if len(ranked) > 1 else None

    return {
        "ok": True,
        "weight_source": weight_source,
        "components": [
            {"key": k, "label": label, "per_share": ps, "weight": w, "equity_value": eq}
            for k, label, ps, w, eq in parts
        ],
        "blended_per_share": blended_price,
        "blended_equity_value": blended_equity,
        "current_price": price,
        "upside": upside,
        "verdict": _verdict(upside),
        "most_bullish": most_bullish,
        "most_bearish": most_bearish,
    }


def _verdict(upside: float | None) -> str:
    if upside is None:
        return "缺少市价，无法比较"
    if upside > 0.30:
        return "显著低估"
    if upside > 0.10:
        return "低估"
    if upside > -0.10:
        return "大致合理"
    if upside > -0.30:
        return "高估"
    return "显著高估"


# ======================================================================
# 敏感性矩阵
# ======================================================================


def sensitivity(fin: Financials, asm: Assumptions, market: str,
                peers: list[Peer], base_wacc: float, base_g: float) -> dict:
    """WACC × 永续增长率 的 5×5 矩阵。

    直接按公式重算，不像 Excel 那样用模拟运算表——每格都是独立结果。
    """
    wacc_axis = [base_wacc + d for d in asm.wacc_steps]
    g_axis = [base_g + d for d in asm.growth_steps]
    axis_source = ("手工指定偏移"
                   if asm.wacc_steps != [-0.01, -0.005, 0.0, 0.005, 0.01] else "默认 ±1.0% / ±0.5%")

    grid, warnings = [], []
    for w in wacc_axis:
        row = []
        for g in g_axis:
            row.append(None if w <= g else _dcf_with(w, g, fin, asm, market, peers))
        grid.append(row)

    if any(v is None for row in grid for v in row):
        warnings.append("部分格子的 WACC 不高于永续增长率，该格无解（已置空）。")

    return {
        "wacc_axis": wacc_axis,
        "growth_axis": g_axis,
        "grid": grid,
        "base_wacc": base_wacc,
        "base_growth": base_g,
        "axis_source": axis_source,
        "unit": "每股价值",
        "warnings": warnings,
    }


def _dcf_with(wacc: float, g: float, fin: Financials, asm: Assumptions,
              market: str, peers: list[Peer]) -> float | None:
    """在给定 WACC / g 下重算每股价值。"""
    sub = Assumptions.from_dict(asm.to_dict())
    sub.terminal_growth = g
    # 用反解的方式把 WACC 强制到目标值：调整 beta
    block = methods.compute_wacc(fin, sub, market)
    base = block["wacc"]
    if base and block["equity_ratio"]:
        # ke 需要调整的量
        erp = block["erp"]
        beta = block["beta"]
        need = wacc - base
        if erp:
            sub.beta = beta + need / (erp * block["equity_ratio"] or 1)
    result = methods.build_dcf(fin, sub, market, peers)
    return result.get("per_share") if result.get("ok") else None


# ======================================================================
# 三情景
# ======================================================================


def scenarios(fin: Financials, asm: Assumptions, market: str, peers: list[Peer]) -> dict:
    """Bull / Base / Bear：收入增速、EBIT 利润率、WACC 三者一起平移。"""
    def run(growth_delta: float, margin_delta: float, wacc_delta: float) -> dict:
        sub = Assumptions.from_dict(asm.to_dict())
        base_y1 = sub.revenue_growth_y1
        if base_y1 is None:
            rev = [v for v in (fin.revenue or []) if v]
            base_y1 = ((rev[-1] / rev[0]) ** (1 / (len(rev) - 1)) - 1) if len(rev) >= 2 else 0.05
        sub.revenue_growth_y1 = base_y1 + growth_delta

        if margin_delta:
            em = sub.ebit_margin
            if em is None:
                em = methods._margin_series(fin, "ebit") or 0.10
            sub.ebit_margin = em + margin_delta

        if wacc_delta:
            # WACC 不是直接输入，用 beta 反解平移
            base_w = methods.compute_wacc(fin, sub, market)
            erp = base_w["erp"]
            if erp and base_w["equity_ratio"]:
                sub.beta = base_w["beta"] + wacc_delta / (erp * base_w["equity_ratio"])

        return methods.build_dcf(fin, sub, market, peers)

    base = run(0.0, 0.0, 0.0)
    bull = run(asm.bull_growth_delta, asm.bull_margin_delta, asm.bull_wacc_delta)
    bear = run(asm.bear_growth_delta, asm.bear_margin_delta, asm.bear_wacc_delta)

    def pack(label: str, result: dict, levers: str) -> dict:
        return {
            "label": label,
            "per_share": result.get("per_share") if result.get("ok") else None,
            "equity_value": result.get("equity_value") if result.get("ok") else None,
            "growth_y1": result.get("revenue_growth_y1"),
            "ebit_margin": result.get("ebit_margin"),
            "wacc": result.get("wacc"),
            "terminal_growth": result.get("terminal_growth"),
            "levers": levers,
        }

    return {
        "bull": pack("乐观", bull,
                     f"收入增速 +{asm.bull_growth_delta:.0%}、EBIT 利润率 "
                     f"+{asm.bull_margin_delta:.0%}、WACC {asm.bull_wacc_delta:+.1%}"),
        "base": pack("基准", base, "历史中位数 / 当前资本结构"),
        "bear": pack("悲观", bear,
                     f"收入增速 {asm.bear_growth_delta:.0%}、EBIT 利润率 "
                     f"{asm.bear_margin_delta:.0%}、WACC {asm.bear_wacc_delta:+.1%}"),
    }


# ======================================================================
# 主入口
# ======================================================================


def value(company, fin: Financials, peers: list[Peer], asm: Assumptions,
          segments: list[SotpSegment], multiples: list[str],
          sources: list[dict] | None = None) -> dict:
    """跑完整套估值，返回统一 JSON。"""
    market = company.market or "A"

    dcf = methods.build_dcf(fin, asm, market, peers)
    relative = methods.build_relative(fin, peers, asm, multiples)
    sotp = methods.build_sotp(fin, segments, asm)

    blended = blend(dcf, relative, sotp, asm, fin)

    sens = {}
    if dcf.get("ok"):
        sens = sensitivity(fin, asm, market, peers,
                           dcf["wacc"], dcf["terminal_growth"])
    scen = {}
    if dcf.get("ok"):
        scen = scenarios(fin, asm, market, peers)

    warnings = []
    for block in (dcf, relative, sotp):
        warnings.extend(block.get("warnings") or [])
    if sotp and sotp.get("skipped"):
        warnings.append(sotp.get("reason"))

    # 方法之间差异过大本身就是重要信号——不能把两个差 4 倍的数简单平均就交出去
    if dcf.get("ok") and relative.get("ok"):
        d, r = dcf.get("per_share"), relative.get("implied_per_share")
        if d and r and min(d, r) > 0:
            gap = max(d, r) / min(d, r) - 1
            if gap > 0.5:
                warnings.append(
                    f"DCF（每股 {d:,.2f}）与相对估值（每股 {r:,.2f}）相差 {gap:.0%}。"
                    "两者背离到这个程度，通常说明：折现率偏低、永续增速偏高，"
                    "或者可比公司选得不对。加权平均值在这种情况下参考价值有限，"
                    "请先定位是哪一头出了问题。"
                )

    return {
        "company": company.to_dict(),
        "as_of": fin.years[-1] if fin.years else None,
        "currency": company.currency,
        # 市场数据单列一块：Excel 底稿要用股本和股价把股权价值换算成每股价值，
        # 早先没导出这两个值，导致底稿里「每股价值」整列空白。
        "market_data": {
            "price": fin.price,
            "shares_outstanding": fin.shares_outstanding,
            "market_cap": fin.market_cap,
            "price_date": company.price_date,
        },
        "dcf": dcf,
        "relative": relative,
        "sotp": sotp,
        "blended": blended,
        "sensitivity": sens,
        "scenarios": scen,
        "warnings": warnings,
        "sources": sources or [],
        "disclaimer": "本结果由模型按既定假设计算，仅供研究与教学用途，不构成投资建议。",
    }
