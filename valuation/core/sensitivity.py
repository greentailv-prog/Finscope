"""敏感性矩阵与三情景。每格独立重算，不用 Excel 模拟运算表。"""
from __future__ import annotations

from .dcf import build_dcf
from .models import Assumptions, Financials, Peer


def _clone(asm: Assumptions) -> Assumptions:
    return Assumptions.from_dict(asm.to_dict())


def _path(y1: float, g: float, n: int) -> list[float]:
    return [y1 + (g - y1) * i / max(n - 1, 1) for i in range(n)]


def wacc_g_matrix(fin: Financials, asm: Assumptions, peers: list[Peer],
                  base_wacc: float, base_growth: float,
                  market: str = "A") -> dict:
    wacc_axis = [base_wacc + d for d in (asm.wacc_steps or [-0.01, -0.005, 0, 0.005, 0.01])]
    g_axis = [base_growth + d for d in (asm.growth_steps or [-0.01, -0.005, 0, 0.005, 0.01])]
    grid = []
    for w in wacc_axis:
        row = []
        for g in g_axis:
            if w <= g + 0.001:
                row.append(None)
                continue
            probe_asm = _clone(asm)
            probe_asm.terminal_growth = g
            probe_asm.revenue_growth_path = _path(probe_asm.revenue_growth_y1, g,
                                                  int(probe_asm.forecast_years or 5))
            probe = build_dcf(fin, probe_asm, market, peers,
                              wacc_override=w, terminal_growth_override=g,
                              solve_implied=False)
            row.append(probe.get("per_share") if probe.get("ok") else None)
        grid.append(row)
    return {
        "kind": "wacc_g",
        "title": "WACC × 永续增长率：每股价值",
        "unit": "元/股",
        "wacc_axis": wacc_axis,
        "growth_axis": g_axis,
        "grid": grid,
        "matrix": grid,
        "base_wacc": base_wacc,
        "base_growth": base_growth,
        "base_index": _base_index(wacc_axis, base_wacc, g_axis, base_growth),
        "note": "行=WACC，列=永续增长率；WACC≤g 的格子无解，写 null。",
    }


def growth_margin_matrix(fin: Financials, asm: Assumptions, peers: list[Peer],
                         base_wacc: float, base_growth: float,
                         market: str = "A") -> dict:
    growth_axis = [(asm.revenue_growth_y1 or 0) + d for d in
                   (asm.growth_steps or [-0.01, -0.005, 0, 0.005, 0.01])]
    margin_axis = [(asm.ebit_margin or 0) + d for d in
                   (asm.growth_steps or [-0.01, -0.005, 0, 0.005, 0.01])]
    grid = []
    n = int(asm.forecast_years or 5)
    for margin in margin_axis:
        row = []
        for growth in growth_axis:
            probe_asm = _clone(asm)
            probe_asm.ebit_margin = margin
            probe_asm.revenue_growth_y1 = growth
            probe_asm.revenue_growth_path = _path(growth, base_growth, n)
            probe = build_dcf(fin, probe_asm, market, peers,
                              wacc_override=base_wacc, terminal_growth_override=base_growth,
                              solve_implied=False)
            row.append(probe.get("per_share") if probe.get("ok") else None)
        grid.append(row)
    return {
        "kind": "growth_margin",
        "title": "首年收入增速 × EBIT 利润率：每股价值",
        "unit": "元/股",
        "growth_axis": growth_axis,
        "margin_axis": margin_axis,
        "grid": grid,
        "matrix": grid,
        "base_growth": asm.revenue_growth_y1,
        "base_margin": asm.ebit_margin,
        "base_index": _base_index(growth_axis, asm.revenue_growth_y1, margin_axis, asm.ebit_margin),
        "note": "行=EBIT 利润率，列=首年收入增速；WACC 与 g 固定在基准值。",
    }


def _base_index(x_axis, x_base, y_axis, y_base):
    def idx(axis, base):
        if base is None:
            return None
        best = min(range(len(axis)), key=lambda i: abs(axis[i] - base))
        return best if abs(axis[best] - base) < 1e-9 else None
    return {"x": idx(x_axis, x_base), "y": idx(y_axis, y_base)}


def scenarios(fin: Financials, asm: Assumptions, peers: list[Peer],
              base_wacc: float, base_growth: float, market: str = "A") -> dict:
    n = int(asm.forecast_years or 5)

    def run(growth_delta: float, margin_delta: float, wacc_delta: float) -> dict:
        sub = _clone(asm)
        y1 = (sub.revenue_growth_y1 or 0) + growth_delta
        sub.revenue_growth_y1 = y1
        sub.revenue_growth_path = _path(y1, base_growth, n)
        sub.ebit_margin = (sub.ebit_margin or 0) + margin_delta
        w = base_wacc + wacc_delta
        probe = build_dcf(fin, sub, market, peers, wacc_override=w,
                          terminal_growth_override=base_growth, solve_implied=False)
        return {
            "per_share": probe.get("per_share") if probe.get("ok") else None,
            "equity_value": probe.get("equity_value") if probe.get("ok") else None,
            "growth_y1": y1,
            "ebit_margin": sub.ebit_margin,
            "wacc": w,
            "terminal_growth": base_growth,
            "ok": probe.get("ok", False),
        }

    base = run(0, 0, 0)
    bull = run(asm.bull_growth_delta, asm.bull_margin_delta, asm.bull_wacc_delta)
    bear = run(asm.bear_growth_delta, asm.bear_margin_delta, asm.bear_wacc_delta)

    # 单调性检查（ABC 规范要求）
    warnings = []
    if all(v.get("per_share") is not None for v in (bull, base, bear)):
        if not (bull["per_share"] >= base["per_share"] >= bear["per_share"]):
            warnings.append("三情景未满足 Bull ≥ Base ≥ Bear 的单调性，请复核假设区间。")
        if not (bull["growth_y1"] > base["growth_y1"] > bear["growth_y1"]):
            warnings.append("三情景的收入增速未满足 Bull > Base > Bear。")
        if not (bull["ebit_margin"] > base["ebit_margin"] > bear["ebit_margin"]):
            warnings.append("三情景的 EBIT 利润率未满足 Bull > Base > Bear。")
        if not (bull["wacc"] < base["wacc"] < bear["wacc"]):
            warnings.append("三情景的 WACC 未满足 Bull < Base < Bear。")

    return {
        "bull": {**bull, "label": "乐观",
                 "levers": f"收入增速 {asm.bull_growth_delta:+.0%}、EBIT 利润率 {asm.bull_margin_delta:+.0%}、WACC {asm.bull_wacc_delta:+.1%}"},
        "base": {**base, "label": "基准", "levers": "历史中位数 / 当前资本结构"},
        "bear": {**bear, "label": "悲观",
                 "levers": f"收入增速 {asm.bear_growth_delta:+.0%}、EBIT 利润率 {asm.bear_margin_delta:+.0%}、WACC {asm.bear_wacc_delta:+.1%}"},
        "warnings": warnings,
    }
