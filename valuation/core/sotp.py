"""分部估值 / SOTP 引擎（v3.1）。
要求两个及以上真实且口径可核验的经营分部；拒绝单一整体“伪SOTP”。
分部财务指标必须对应估值倍数，独立确认集团费用、抵销项、净债务。
分部收入覆盖及净资产转换不满足要求则阻断，不输出未经核验的单点估值。
"""
from __future__ import annotations

from statistics import median

from .metrics import safe_div
from .models import Assumptions, Financials, Segment


def allocate_segment_ebit(segments: list[Segment], total_ebit: float | None,
                          allocation: str = "gross_profit",
                          total_da: float | None = None) -> None:
    """把公司整体 EBIT / D&A 按毛利或收入占比分摊到各分部（规则披露）。"""
    if not segments:
        return
    if allocation == "gross_profit":
        weights = [max(s.gross_profit or 0.0, 0.0) for s in segments]
    else:
        weights = [max(s.revenue or 0.0, 0.0) for s in segments]
    total = sum(weights)
    if total <= 0:
        return
    for s, w in zip(segments, weights):
        if total_ebit is not None:
            s.ebit = total_ebit * w / total
        if total_da is not None:
            s.ebitda = (s.ebit or 0.0) + total_da * w / total
        elif s.ebit is not None:
            s.ebitda = s.ebit


def build_sotp(fin: Financials, segments: list[Segment], asm: Assumptions,
               fallback_ev_revenue: float | None = None,
               fallback_ev_ebitda: float | None = None) -> dict:
    warnings: list[str] = []
    if len(segments) < 2 or any((s.name or "").startswith(("整体业务", "未分配/内部抵销"))
                                for s in segments):
        return {"ok": False, "status": "blocked", "skipped": True,
                "reason": "真实SOTP至少需要两个可独立核验的业务分部；整体业务/推算补差不是分部。",
                "warnings": ["停止伪分部估值，不将单一整体业务视为SOTP。"]}
    if not segments:
        return {
            "ok": False,
            "skipped": True,
            "reason": "未取得分部收入数据，SOTP 不可用。",
            "warnings": ["未取得分部数据，SOTP 未参与融合。"],
        }

    total_revenue = fin.latest(fin.revenue)
    total_ebit = fin.latest(fin.ebit)
    total_da = fin.latest(fin.da)
    # 不覆盖上游已披露的分部利润。若需分摊，必须单独显式启用并标注估算。
    if asm.segment_allocation in ("gross_profit", "revenue"):
        allocate_segment_ebit(segments, total_ebit, asm.segment_allocation, total_da=total_da)

    if fin.cash is None or fin.total_debt is None or not fin.shares_outstanding:
        return {"ok": False, "status": "blocked", "reason": "缺少净债务或总股本，无法转化股权价值。"}
    rows = []
    total_ev = 0.0
    covered_revenue = 0.0
    for seg in segments:
        # 倍数与财务指标必须严格对应；不能把 EV/EBITDA 当 EV/EBIT 使用。
        # 用户手工指定分部倍数时也不能被自动探测到的 EBITDA 倍数覆盖。
        multiple_type = seg.multiple_type or ("ev_revenue" if seg.metric == "revenue" else "ev_ebit")
        if multiple_type == "ev_revenue":
            value = seg.revenue if seg.revenue is not None else (seg.value if seg.metric == "revenue" else None)
            multiple = seg.multiple if seg.multiple is not None else seg.peer_median_ev_revenue
        elif multiple_type == "ev_ebitda":
            value = seg.ebitda if seg.ebitda is not None else (seg.value if seg.metric == "ebitda" else None)
            multiple = seg.multiple if seg.multiple is not None else seg.peer_median_ev_ebitda
        elif multiple_type == "ev_ebit":
            value = seg.ebit if seg.ebit is not None else (seg.value if seg.metric == "ebit" else None)
            multiple = seg.multiple  # 未提供纯业务 EV/EBIT 就停止；不可套 EV/EBITDA
        else:
            warnings.append(f"分部「{seg.name or '未命名'}」使用了不支持的倍数 {multiple_type}，已跳过。")
            continue
        if value is None or value <= 0 or not multiple or multiple <= 0:
            warnings.append(f"分部「{seg.name or '未命名'}」缺指标值或可比倍数，已跳过该分部。")
            continue
        seg_ev = value * multiple
        total_ev += seg_ev
        covered_revenue += seg.revenue or 0.0
        rows.append({
            "name": seg.name,
            "level": seg.level,
            "parent": seg.parent,
            "metric": seg.metric,
            "metric_basis": ("ebitda" if multiple_type == "ev_ebitda"
                             else "ebit" if multiple_type == "ev_ebit"
                             else "revenue"),
            "value": value,
            "multiple_type": multiple_type,
            "multiple": multiple,
            "peer_names": seg.peer_names,
            "peer_tickers": seg.peer_tickers,
            "peer_median_ev_revenue": seg.peer_median_ev_revenue,
            "peer_median_ev_ebitda": seg.peer_median_ev_ebitda,
            "segment_ev": seg_ev,
            "revenue": seg.revenue,
            "gross_profit": seg.gross_profit,
            "gross_margin": seg.gross_margin,
            "revenue_share": seg.revenue_share,
            "allocated_ebit": seg.ebit,
            "allocated_ebitda": seg.ebitda,
            "note": seg.note,
            "source": seg.source,
            "as_of": seg.as_of,
        })

    if not rows:
        return {
            "ok": False,
            "error": "没有可用的分部数据",
            "reason": "分部数据或倍数缺失，SOTP 无法计算。",
            "warnings": warnings,
        }

    # 覆盖度：分部收入合计 / 公司营业收入
    coverage = safe_div(covered_revenue, total_revenue) if total_revenue else None
    if coverage is not None and coverage < 0.80:
        warnings.append(
            f"分部收入合计仅覆盖公司营业收入的 {coverage:.0%}，可能有未分配/内部抵销项目，"
            "SOTP 结论的代表性下降。"
        )
    if coverage is not None and coverage > 1.05:
        warnings.append(
            f"分部收入合计为公司营业收入的 {coverage:.0%}，超过 100%，可能存在内部交易未抵销，"
            "请核对年报分部附注。"
        )

    # 总部费用必须经单独确认。自动百分比扣减可能重复计入经营利润。
    corporate_cost = asm.sotp_corporate_cost
    if corporate_cost is None:
        return {"ok": False, "status": "blocked", "reason": "未确认总部费用是否已计入分部 EBIT，停止 SOTP。",
                "warnings": warnings + ["请提供总部费用现值，或确认已经含于各分部利润后显式指定 0。"],
                "rows": rows, "segment_ev_total": total_ev, "revenue_coverage": coverage}
    if corporate_cost < 0:
        return {"ok": False, "status": "blocked", "reason": "总部费用扣减不得为负。"}

    if coverage is None or not (0.85 <= coverage <= 1.05) or len(rows) < 2 or len(rows) != len(segments):
        return {"ok": False, "status": "blocked", "reason": "分部收入覆盖/样本完整性未达闸门要求。",
                "warnings": warnings, "rows": rows, "revenue_coverage": coverage}
    net_debt = fin.net_debt()
    minority = fin.minority_interest or 0.0
    preferred = fin.preferred_stock or 0.0
    equity = total_ev - corporate_cost - net_debt - minority - preferred
    per_share = safe_div(equity, fin.shares_outstanding)
    if equity <= 0 or per_share is None or per_share <= 0:
        return {"ok": False, "status": "blocked", "reason": "SOTP 股权价值不大于0，须核验分部口径、集团费用及净负债。",
                "diagnostic_values": {"segment_ev_total": total_ev, "corporate_cost": corporate_cost,
                                      "net_debt": net_debt, "equity_value": equity}, "warnings": warnings}
    price = fin.price
    discount = safe_div(per_share - price, per_share) if (per_share and price) else None
    if discount is not None and abs(discount) > 1.0:
        warnings.append(
            f"SOTP 每股价值 {per_share:,.2f} 元与现价 {price:,.2f} 元相差 {discount:.0%}，"
            "差异过大，分部倍数、总部费用或收入口径很可能需要复核；该结果不建议单独使用。"
        )

    # 分部倍数的一致性：用合计 EV / 公司整体指标，和直接倍数比较
    implied_ev_revenue = safe_div(total_ev, total_revenue)
    implied_ev_ebitda = safe_div(total_ev, fin.ebitda_latest())
    if implied_ev_revenue and fallback_ev_revenue:
        gap = implied_ev_revenue / fallback_ev_revenue - 1
        if abs(gap) > 0.5:
            warnings.append(
                f"SOTP 合计隐含 EV/收入 {implied_ev_revenue:.1f}x，与公司整体同业中位 "
                f"{fallback_ev_revenue:.1f}x 相差 {gap:.0%}，分部倍数或收入口径需复核。"
            )

    return {
        "ok": True,
        "method": "sotp",
        "status": "ok",
        "rows": rows,
        "segment_count": len(rows),
        "segment_ev_total": total_ev,
        "corporate_cost": corporate_cost,
        "corporate_cost_estimated": corporate_cost > 0,
        "net_debt": net_debt,
        "minority_interest": minority,
        "preferred_stock": preferred,
        "equity_value": equity,
        "per_share": per_share,
        "conglomerate_discount": discount,
        "revenue_coverage": coverage,
        "implied_ev_revenue": implied_ev_revenue,
        "implied_ev_ebitda": implied_ev_ebitda,
        "allocation_rule": ("按各分部毛利占比分摊公司 EBIT" if asm.segment_allocation == "gross_profit"
                            else "按各分部收入占比分摊公司 EBIT"),
        "warnings": warnings,
    }
