"""把「主营构成」原始行整理成 SOTP 可用的分部结构。

规则：
  · 优先顶层产品分类；如果某个顶层下面有 >=2 个「其中:」子项，且子项合计
    覆盖该顶层 >=80% 收入，则展开子项（例如美的的「商业及工业解决方案」）；
  · 分部收入合计不足公司总收入的 80% 时，补一个「未分配/抵销」分部，
    避免 SOTP 凭空少算一块；
  · 完全没有分部数据时，构造一个「整体业务（未拆分）」分部，明确标注这不
    是真正的 SOTP，由可靠性评分把权重压下来。
"""
from __future__ import annotations

from ..core.models import Financials, Segment


def _sum(rows):
    return sum(r.get("revenue") or 0 for r in rows)


def _choose_rows(raw_rows: list[dict]) -> list[dict]:
    tops = [r for r in raw_rows if r.get("level") == "top"]
    children = [r for r in raw_rows if r.get("level") == "child"]
    if not tops:
        return raw_rows

    chosen = []
    for top in tops:
        kids = [c for c in children if c.get("parent") == top["name"]]
        if len(kids) >= 2 and _sum(kids) >= (top.get("revenue") or 0) * 0.80:
            chosen.extend(kids)
        else:
            chosen.append(top)
    return chosen


def build_segments(raw_rows: list[dict] | None, fin: Financials,
                   total_revenue: float | None = None,
                   max_segments: int = 8) -> tuple[list[Segment], dict]:
    total_revenue = total_revenue or fin.latest(fin.revenue)
    rows = _choose_rows(list(raw_rows or []))
    # 去掉明显重复/合计行
    rows = [r for r in rows if r.get("revenue") and r["revenue"] > 0]
    rows.sort(key=lambda r: r.get("revenue") or 0, reverse=True)

    # 超过上限时，把最小的合并成「其他业务」
    if len(rows) > max_segments:
        keep = rows[: max_segments - 1]
        rest = rows[max_segments - 1:]
        merged = {
            "name": "其他业务（合并）",
            "level": "top",
            "parent": "",
            "revenue": _sum(rest),
            "gross_profit": sum(r.get("gross_profit") or 0 for r in rest) or None,
            "gross_margin": None,
            "revenue_share": None,
            "period": rest[0].get("period") if rest else "",
            "source": rest[0].get("source") if rest else "",
        }
        rows = keep + [merged]

    total_gp = sum(r.get("gross_profit") or 0 for r in rows) or None
    for r in rows:
        r["revenue_share"] = (r["revenue"] / total_revenue) if total_revenue else None
        if r.get("gross_profit") is None and r.get("gross_margin") is not None:
            r["gross_profit"] = r["revenue"] * r["gross_margin"]

    segments = []
    for r in rows:
        segments.append(Segment(
            name=r.get("name") or "",
            level=r.get("level") or "top",
            parent=r.get("parent") or "",
            metric="revenue",
            value=r.get("revenue"),
            revenue=r.get("revenue"),
            gross_profit=r.get("gross_profit"),
            gross_margin=(r.get("gross_profit") / r["revenue"]) if r.get("gross_profit") and r.get("revenue") else r.get("gross_margin"),
            revenue_share=r.get("revenue_share"),
            multiple_type="ev_revenue",
            note="分部利润未披露，使用 EV/Revenue；EBIT 按毛利占比分摊",
            source=r.get("source") or "东方财富·主营构成",
            as_of=str(r.get("period") or "")[:10],
        ))

    # 不再自动补一个“未分配/内部抵销”虚构分部进入估值。
    # 覆盖缺口记录在 meta，交由 SOTP 完整性闸门处理。
    covered = sum(s.revenue or 0 for s in segments)
    coverage = (covered / total_revenue) if total_revenue else None

    meta = {
        "raw_count": len(raw_rows or []),
        "chosen_count": len(segments),
        "covered_revenue": sum(s.revenue or 0 for s in segments),
        "total_revenue": total_revenue,
        "coverage": (sum(s.revenue or 0 for s in segments) / total_revenue) if total_revenue else None,
        "expanded_children": any(s.level == "child" for s in segments),
    }
    return segments, meta


def fallback_single_segment(fin: Financials) -> tuple[list[Segment], dict]:
    revenue = fin.latest(fin.revenue)
    if not revenue:
        return [], {"coverage": None, "fallback": True}
    gm = None
    if fin.latest(fin.gross_profit) is not None and revenue:
        gm = fin.latest(fin.gross_profit) / revenue
    seg = Segment(
        name="整体业务（未拆分）",
        metric="revenue",
        value=revenue,
        revenue=revenue,
        gross_profit=(revenue * gm) if gm else None,
        gross_margin=gm,
        revenue_share=1.0,
        multiple_type="ev_revenue",
        note="未取得分部数据；按公司整体 EV/Revenue 估值。这不是真正的 SOTP，可靠性评分会降权。",
        source="规则兜底",
        as_of="",
    )
    return [seg], {"coverage": 1.0, "fallback": True, "chosen_count": 1}
