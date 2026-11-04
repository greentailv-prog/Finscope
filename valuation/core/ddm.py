"""DDM / 剩余收益：金融行业的「绝对估值」替代。

银行、保险、证券的有息负债是经营资金，标准 FCFF/WACC 不成立（见 RULES.md）。
这里用两把尺子：
  · 稳定增长 DDM：股权价值 = 下一期股利 / (Ke − g)
  · 剩余收益（RI）：股权价值 = 账面权益 + 账面权益 × (ROE − Ke) / (Ke − g)
两者取中点，既能反映分红能力，也能反映超额 ROE。

金融行业的 CAPM 股权成本在低利率环境下经常显著低于市场隐含的股权成本
（市场对资产质量、久期、监管资本要求定价）。因此与 DCF 一样，加入
「市场隐含 Ke 校准」：差距超过 150bp 时按规则向市场隐含值靠拢，并披露两个值。
"""
from __future__ import annotations

from statistics import median

from . import defaults
from .metrics import clamp, safe_div
from .models import Assumptions, Financials


def _value_at(ke: float, g: float, ni: float, payout: float,
              equity_book: float, roe: float) -> float | None:
    if ke <= g + 0.002:
        return None
    ddm = ni * payout * (1 + g) / (ke - g)
    ri = equity_book + equity_book * (roe - ke) / (ke - g)
    vals = [v for v in (ddm, ri) if v is not None and v > 0]
    return median(vals) if vals else None


def _solve_implied_ke(g: float, ni: float, payout: float,
                      equity_book: float, roe: float,
                      target: float) -> float | None:
    lo, hi = max(g + 0.005, 0.02), 0.60
    best = None
    for _ in range(70):
        mid = (lo + hi) / 2
        v = _value_at(mid, g, ni, payout, equity_book, roe)
        if v is None:
            lo = mid
            continue
        if v > target:
            lo = mid      # Ke 太低 → 估值太高 → 提高 Ke
        else:
            hi = mid
        best = mid
    return round((lo + hi) / 2, 6) if best is not None else None


def build_ddm(fin: Financials, asm: Assumptions, market: str = "A") -> dict:
    warnings: list[str] = []
    net_income = fin.latest(fin.net_income)
    equity_book = fin.total_equity
    if net_income is None or net_income <= 0:
        return {"ok": False, "error": "净利润为负或缺失，DDM/剩余收益不适用。",
                "warnings": ["金融行业绝对估值需要正的净利润。"]}
    if not equity_book or equity_book <= 0:
        return {"ok": False, "error": "净资产为负或缺失，剩余收益模型不适用。",
                "warnings": ["缺少账面净资产，无法计算 DDM/RI。"]}

    mkt = defaults.market_defaults(market)
    ke_capm = getattr(asm, "_ke", None)
    if ke_capm is None:
        ke_capm = (asm.risk_free or mkt["risk_free"]) + (asm.beta or 1.0) * (asm.erp or mkt["erp"])
    ke_capm = clamp(ke_capm, 0.04, 0.30)

    # 分红率：优先用现金流量表的股利支付，其次用假设，最后 30%
    payout = asm.dividend_payout
    if payout is None:
        div = fin.latest(fin.dividends_paid)
        if div and div > 0 and net_income > 0:
            probe = div / net_income
            if 0 < probe <= 1.0:
                payout = clamp(probe, 0.0, 1.0)
                payout_source = f"现金流量表股利支付 / 净利润 = {payout:.1%}"
            else:
                payout, payout_source = 0.30, "股利支付率异常，按 30% 估算"
        else:
            payout, payout_source = 0.30, "缺股利数据，按 30% 估算"
    else:
        payout_source = "使用者指定"
    payout = clamp(payout, 0.0, 1.0)

    g = asm.ddm_growth if asm.ddm_growth is not None else (asm.terminal_growth or 0.03)
    g = clamp(g, 0.0, min(0.06, mkt["terminal_growth_cap"]))

    # ---- 市场隐含 Ke 校准 ----
    implied_ke = None
    if fin.market_cap and fin.shares_outstanding:
        implied_ke = _solve_implied_ke(g, net_income, payout, equity_book,
                                       safe_div(net_income, equity_book) or 0.10,
                                       fin.market_cap)
    ke = ke_capm
    reconciliation = None
    if implied_ke is not None and abs(implied_ke - ke_capm) > 0.015:
        gap = implied_ke - ke_capm
        # 金融行业的市场隐含 Ke 与 CAPM 差距可能很大（资产质量/久期风险），
        # 允许更大的校准幅度（最多 8%），但仍保留 CAPM 作为下界参考。
        adjust = clamp(gap * 0.60, -0.08, 0.08)
        ke = ke_capm + adjust
        reconciliation = {
            "ke_capm": ke_capm,
            "implied_ke": implied_ke,
            "gap": gap,
            "adjustment": adjust,
            "applied": True,
            "rule": f"CAPM Ke {ke_capm:.2%} 与市场隐含 Ke {implied_ke:.2%} 相差 "
                    f"{abs(gap) * 10000:.0f}bp，规则校准至 {ke:.2%}",
        }
    ke = clamp(ke, 0.04, 0.30)

    if ke <= g + 0.005:
        new_g = max(0.0, ke - 0.01)
        warnings.append(f"Ke（{ke:.2%}）与增长率（{g:.2%}）过于接近，已把 g 下调至 {new_g:.2%}。")
        g = new_g

    roe = safe_div(net_income, equity_book)
    ddm_value = net_income * payout * (1 + g) / (ke - g)
    ri_value = None
    if roe is not None:
        ri_value = equity_book + equity_book * (roe - ke) / (ke - g)
        if ri_value <= 0:
            ri_value = None

    components = [v for v in (ddm_value, ri_value) if v is not None and v > 0]
    equity = median(components) if components else None
    per_share = safe_div(equity, fin.shares_outstanding)

    if ddm_value and ri_value:
        gap = abs(ddm_value - ri_value) / max(ddm_value, ri_value)
        if gap > 0.35:
            warnings.append(
                f"DDM（{ddm_value / 1e8:,.0f} 亿元）与剩余收益（{ri_value / 1e8:,.0f} 亿元）"
                f"相差 {gap:.0%}，分红率或 ROE 假设需复核；已取中点。"
            )
    if reconciliation:
        warnings.append(reconciliation["rule"] + "。金融行业的市场隐含 Ke 通常反映资产质量与久期风险。")
    if payout_source.startswith("缺股利") or payout_source.startswith("股利支付率异常"):
        warnings.append(f"分红率按规则估算：{payout_source}。银行估值对分红率高度敏感。")

    return {
        "ok": True,
        "method": "ddm",
        "status": "ok",
        "per_share": per_share,
        "equity_value": equity,
        "cost_of_equity": ke,
        "cost_of_equity_capm": ke_capm,
        "implied_cost_of_equity": implied_ke,
        "ke_reconciliation": reconciliation,
        "growth": g,
        "payout_ratio": payout,
        "payout_source": payout_source,
        "roe": roe,
        "book_equity": equity_book,
        "net_income": net_income,
        "ddm_value": ddm_value,
        "ri_value": ri_value,
        "components": [
            {"name": "稳定增长 DDM", "equity_value": ddm_value,
             "per_share": safe_div(ddm_value, fin.shares_outstanding)},
            {"name": "剩余收益 RI", "equity_value": ri_value,
             "per_share": safe_div(ri_value, fin.shares_outstanding)},
        ],
        "warnings": warnings,
        "note": "金融行业标准 FCFF/WACC 不适用，使用 DDM 与剩余收益作为绝对估值替代。",
    }
