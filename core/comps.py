"""相对估值 / Comps 引擎（v2）。

支持 PE、前瞻 PE、PEG、PB、PS、PCF、EV/Revenue、EV/EBITDA、EV/EBIT。
规则：
  · 同业取中位数，同时给均值/四分位/离散度；
  · 目标与同业增速/利润率差异明显时，自动做温和倍数调整并说明理由；
  · 负净利润跳过 PE/PEG，负 EBITDA 跳过 EV/EBITDA，不伪造；
  · 金融行业不适用 EV 类倍数（债务是经营资金）；
  · 每个倍数都输出 sample_count、peer_median、metric_basis、被剔除样本。
"""
from __future__ import annotations

import math

from statistics import mean, median

from . import defaults
from .metrics import (
    clean, clamp, dispersion, mean_of, median_of, percentile, percentile_rank,
    safe_div,
)
from .models import Assumptions, Financials, Peer

MULTIPLE_LABELS = {
    "pe": "市盈率 PE",
    "pe_forward": "前瞻市盈率",
    "peg": "PEG",
    "pb": "市净率 PB",
    "ps": "市销率 PS",
    "pcf": "市现率 PCF",
    "ev_revenue": "EV/营业收入",
    "ev_ebitda": "EV/EBITDA",
    "ev_ebit": "EV/EBIT",
}

_METRIC_KEY = {
    "pe": "net_income",
    "pe_forward": "net_income",
    "peg": "net_income",
    "pb": "equity",
    "ps": "revenue",
    "pcf": "cfo",
    "ev_revenue": "revenue",
    "ev_ebitda": "ebitda",
    "ev_ebit": "ebit",
}

_FINANCIAL_MULTIPLES = {"pe", "pe_forward", "peg", "pb"}


def target_metrics(fin: Financials) -> dict:
    revenue = fin.latest(fin.revenue)
    # 股权 PE 对应归母净利润；合并净利润可能含少数股东损益。
    net_income = fin.latest(fin.net_income_parent)
    if net_income is None:
        net_income = fin.latest(fin.net_income)
    ebit = fin.latest(fin.ebit)
    da = fin.latest(fin.da)
    ebitda = (ebit + da) if (ebit is not None and da is not None) else None
    equity = fin.total_equity
    cfo = fin.latest(fin.cfo)
    return {
        "revenue": revenue,
        "net_income": net_income,
        "ebit": ebit,
        "da": da,
        "ebitda": ebitda,
        "equity": equity,
        "cfo": cfo,
        "net_debt": fin.net_debt(),
    }


def target_multiples(fin: Financials, growth: float | None = None) -> dict:
    """目标公司自己的倍数，用于和同业分布比较。"""
    m = target_metrics(fin)
    cap = fin.market_cap or safe_div((fin.price or 0) * (fin.shares_outstanding or 0), 1)
    ev = None
    if cap is not None and fin.total_debt is not None and fin.cash is not None:
        ev = cap + fin.total_debt - fin.cash + (fin.minority_interest or 0) + (fin.preferred_stock or 0)
    out = {
        "pe": safe_div(cap, m["net_income"]) if m["net_income"] and m["net_income"] > 0 else None,
        "pb": safe_div(cap, m["equity"]) if m["equity"] and m["equity"] > 0 else None,
        "ps": safe_div(cap, m["revenue"]) if m["revenue"] and m["revenue"] > 0 else None,
        "pcf": safe_div(cap, m["cfo"]) if m["cfo"] and m["cfo"] > 0 else None,
        "ev_revenue": safe_div(ev, m["revenue"]) if ev and m["revenue"] and m["revenue"] > 0 else None,
        "ev_ebitda": safe_div(ev, m["ebitda"]) if ev and m["ebitda"] and m["ebitda"] > 0 else None,
        "ev_ebit": safe_div(ev, m["ebit"]) if ev and m["ebit"] and m["ebit"] > 0 else None,
        "market_cap": cap,
        "enterprise_value": ev,
    }
    # 禁止用营业收入增长率冒充净利润增长率；目标PEG须另取明确盈利预测。
    out["peg"] = None
    return out


def choose_multiples(fin: Financials, peers: list[Peer], user_multiples: list[str] | None,
                     industry_support: str = "supported") -> tuple[list[str], list[dict]]:
    """按规则选择适用倍数；用户指定则优先用户，但仍剔除结构上不适用的。"""
    m = target_metrics(fin)
    industry_text = fin.industry or ""
    is_financial = any(k in industry_text for k in ("银行", "保险", "证券", "券商"))
    # 目标自身特征
    profitable = (m["net_income"] or 0) > 0
    positive_equity = (m["equity"] or 0) > 0
    positive_revenue = (m["revenue"] or 0) > 0
    positive_ebitda = (m["ebitda"] or 0) > 0
    positive_cfo = (m["cfo"] or 0) > 0
    growth = None
    if fin.revenue and len(fin.revenue) >= 2 and fin.revenue[-2]:
        growth = fin.revenue[-1] / fin.revenue[-2] - 1

    rules = defaults.sector_params().get("default_multiples", {})
    if user_multiples:
        candidates = list(user_multiples)
        source = "使用者指定"
    elif is_financial:
        candidates = list(rules.get("financial", ["pb", "pe"]))
        source = "规则：金融行业使用 PB/PE，不使用 EV 类倍数"
    elif not profitable:
        candidates = list(rules.get("loss_making", ["ps", "ev_revenue", "pb"]))
        source = "规则：净利润为负，跳过 PE/PEG，使用 PS/EV-Revenue/PB"
    elif growth is not None and growth > 0.20:
        candidates = list(rules.get("high_growth", ["ps", "ev_revenue", "ev_ebitda", "peg"]))
        source = "规则：高增长，优先 PS/EV-Revenue/EV-EBITDA/PEG"
    elif (m["da"] or 0) and (m["revenue"] or 0) and (m["da"] / m["revenue"]) > 0.08:
        candidates = list(rules.get("capital_intensive", ["ev_ebitda", "pe", "pb", "ps"]))
        source = "规则：重资产（折旧摊销占收入>8%），优先 EV/EBITDA"
    else:
        candidates = list(rules.get("profitable", ["pe", "ps", "pb", "ev_ebitda"]))
        source = "规则：盈利稳定，使用 PE/PS/PB/EV-EBITDA"

    target_margin = safe_div(m["ebit"], m["revenue"])
    target_roe = safe_div(m["net_income"], m["equity"])
    da_ratio = safe_div(m["da"], m["revenue"])
    capex_ratio = safe_div(fin.latest(fin.capex), m["revenue"])
    asset_light = ((da_ratio is not None and da_ratio < 0.05)
                   or (capex_ratio is not None and capex_ratio < 0.05)
                   or (target_margin is not None and target_margin > 0.40))
    decisions = []
    chosen = []
    for key in candidates:
        key = key.strip()
        if key not in MULTIPLE_LABELS:
            continue
        meta = defaults.multiple_meta(key)
        reason = "适用"
        ok = True
        if target_margin is not None and target_margin > 0.50 and key in ("ps", "ev_revenue"):
            ok, reason = False, ("目标 EBIT 利润率超过 50%，销售类倍数无法反映高毛利结构的价值，"
                                 "仅作参考，不参与结论")
        elif (not is_financial and key == "pb" and target_roe is not None
              and target_roe > 0.25 and asset_light):
            ok, reason = False, ("目标 ROE 超过 25% 且为轻资产（D&A/收入<5%），"
                                 "PB 主要反映账面价值而非盈利能力，仅作参考，不参与结论")
        elif is_financial and key not in _FINANCIAL_MULTIPLES:
            ok, reason = False, "金融行业不适用：有息负债是经营资金，EV 口径失真"
        elif key in ("pe", "pe_forward", "peg") and not profitable:
            ok, reason = False, "目标净利润为负，PE/PEG 无意义"
        elif key == "peg" and (growth is None or growth <= 0):
            ok, reason = False, "目标增速缺失或为负，PEG 无意义"
        elif key == "pb" and not positive_equity:
            ok, reason = False, "目标净资产为负"
        elif key in ("ps", "ev_revenue") and not positive_revenue:
            ok, reason = False, "目标营业收入缺失"
        elif key == "pcf" and not positive_cfo:
            ok, reason = False, "目标经营现金流为负或缺失"
        elif key in ("ev_ebitda",) and not positive_ebitda:
            ok, reason = False, "目标 EBITDA 为负或缺失"
        elif key == "ev_ebit" and not ((m["ebit"] or 0) > 0):
            ok, reason = False, "目标 EBIT 为负或缺失"
        if ok:
            # 检查同业是否有有效样本
            valid = [getattr(p, key) for p in peers if getattr(p, key) is not None and getattr(p, key) > 0]
            if len(valid) < 2:
                ok, reason = False, f"同业有效样本不足（{len(valid)} 家）"
        decisions.append({
            "multiple": key,
            "label": MULTIPLE_LABELS[key],
            "used": ok,
            "reason": reason,
        })
        if ok:
            chosen.append(key)
    return chosen, [{"source": source, "decisions": decisions}]


def _peer_stat(peers: list[Peer], key: str) -> dict:
    vals = []
    excluded = []
    rule = defaults.peer_rules()
    limit = rule["outlier_pe_max"] if key.startswith("pe") else (
        rule["outlier_ev_revenue_max"] if key == "ev_revenue" else None)
    for p in peers:
        raw = getattr(p, key, None)
        if raw is None or raw <= 0:
            if raw is not None:
                excluded.append({"name": p.name, "ticker": p.ticker, "value": raw, "reason": "非正值"})
            continue
        if limit and raw > limit:
            excluded.append({"name": p.name, "ticker": p.ticker, "value": raw,
                             "reason": f"超过异常阈值 {limit:g}x"})
            continue
        vals.append(raw)
    return {
        "median": median(vals) if vals else None,
        "mean": mean(vals) if vals else None,
        "p25": percentile(vals, 0.25),
        "p75": percentile(vals, 0.75),
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
        "count": len(vals),
        "values": vals,
        "dispersion": dispersion(vals),
        "excluded": excluded,
    }


def _auto_adjustment(key: str, fin: Financials, peers: list[Peer],
                     target_growth: float | None) -> tuple[float, str]:
    """目标与同业在增速/利润率上的差异 → 温和倍数调整。"""
    if key not in ("pe", "pe_forward", "peg", "ps", "ev_revenue", "ev_ebitda", "ev_ebit"):
        return 0.0, "PB/PCF 不做成长性调整，保持同业中位数"
    # 同业增速先剔除口径异常/极端值，避免五粮液 -55% 这类样本把中位数拉偏
    growth_vals = [p.revenue_growth for p in peers
                   if p.revenue_growth is not None and -0.40 <= p.revenue_growth <= 1.50]
    peer_growth = median_of(growth_vals)
    peer_margin = median_of([p.ebit_margin for p in peers if p.ebit_margin is not None])
    tgt_margin = safe_div(fin.latest(fin.ebit), fin.latest(fin.revenue))
    adjust = 0.0
    reasons = []
    if target_growth is not None and peer_growth is not None:
        diff = target_growth - peer_growth
        if diff > 0.05:
            a = min(0.30, (diff - 0.05) * 1.5)
            adjust += a
            reasons.append(f"目标增速 {target_growth:.1%} 高于同业中位 {peer_growth:.1%} {diff * 100:.0f}pp，上调 {a:.0%}")
        elif diff < -0.05:
            a = max(-0.30, (diff + 0.05) * 1.5)
            adjust += a
            reasons.append(f"目标增速 {target_growth:.1%} 低于同业中位 {peer_growth:.1%} {abs(diff) * 100:.0f}pp，下调 {abs(a):.0%}")
    if tgt_margin is not None and peer_margin is not None:
        diff = tgt_margin - peer_margin
        if diff > 0.03:
            a = min(0.20, (diff - 0.03) * 1.0)
            adjust += a
            reasons.append(f"目标 EBIT 利润率 {tgt_margin:.1%} 高于同业 {peer_margin:.1%}，上调 {a:.0%}")
        elif diff < -0.03:
            a = max(-0.20, (diff + 0.03) * 1.0)
            adjust += a
            reasons.append(f"目标 EBIT 利润率 {tgt_margin:.1%} 低于同业 {peer_margin:.1%}，下调 {abs(a):.0%}")
    adjust = clamp(adjust, -0.30, 0.30)
    return adjust, "；".join(reasons) if reasons else "目标与同业增速/利润率接近，不调整"


def build_comps(fin: Financials, peers: list[Peer], asm: Assumptions,
                multiples: list[str] | None = None,
                industry_support: str = "supported",
                peer_selection: dict | None = None,
                target_growth: float | None = None) -> dict:
    peer_selection = dict(peer_selection or {})
    if peer_selection.get("peers"):
        peer_selection["peers"] = [
            p.to_dict() if hasattr(p, "to_dict") else p for p in peer_selection["peers"]
        ]

    if (peer_selection.get("tier") in {"proxy", "review_required", "user_failed"}):
        return {"ok": False, "status": "blocked", "error": "同业业务可比性尚未核验，停止相对估值。",
                "peer_selection": peer_selection, "warnings": ["禁止使用板块代理样本直接计算目标价。"]}
    if not peers:
        return {
            "ok": False,
            "error": "没有可比公司样本",
            "reason": "无可用同业样本",
            "warnings": ["规则层未能构造可比公司样本，相对估值不可用。"],
        }

    chosen, decision_blocks = choose_multiples(fin, peers, multiples, industry_support)
    if not chosen:
        return {
            "ok": False,
            "error": "所有选用倍数都不适用",
            "reason": "所有选用倍数都因目标指标为负或同业样本不足而被剔除",
            "decisions": decision_blocks,
            "warnings": ["相对估值的候选倍数全部不适用。"],
        }

    m = target_metrics(fin)
    net_debt = m["net_debt"]
    cap = fin.market_cap or safe_div((fin.price or 0) * (fin.shares_outstanding or 0), 1)
    warnings: list[str] = []
    if any(not p.as_of or not p.source for p in peers):
        warnings.append("部分同业缺取数日期或来源，须核验基准日与 LYR/TTM 口径；此轮结果仅供预审。")
    results = []
    peer_table = []

    # 同业明细表（无论是否采用，都披露）
    for p in peers:
        peer_table.append({
            "name": p.name,
            "ticker": p.ticker,
            "industry": p.industry,
            "market_cap": p.market_cap,
            "pe": p.pe,
            "pb": p.pb,
            "ps": p.ps,
            "pcf": p.pcf,
            "peg": p.peg,
            "ev_revenue": p.ev_revenue,
            "ev_ebitda": p.ev_ebitda,
            "ev_ebit": p.ev_ebit,
            "revenue_growth": p.revenue_growth,
            "net_income_growth": p.net_income_growth,
            "gross_margin": p.gross_margin,
            "ebitda_margin": p.ebitda_margin,
            "ebit_margin": p.ebit_margin,
            "roe": p.roe,
            "selection_reason": p.selection_reason,
            "selection_score": p.selection_score,
            "tier": p.tier,
            "caliber": p.caliber,
            "source": p.source,
            "as_of": p.as_of,
            "data_ok": p.data_ok,
        })

    # 可比性评分：行业 + 规模 + 增速 + 利润率，给前端逐家解释
    target_cap = fin.market_cap
    target_margin = safe_div(m.get("ebit"), m.get("revenue"))
    for p in peer_table:
        score = 100.0
        reasons = []
        if target_cap and p.get("market_cap"):
            ratio = p["market_cap"] / target_cap
            if ratio > 0:
                penalty = min(25.0, abs(math.log10(ratio)) * 14)
                if penalty > 3:
                    score -= penalty
                    reasons.append(f"规模为目标公司的 {ratio:.2f}×（-{penalty:.0f}）")
                else:
                    reasons.append(f"规模接近（{ratio:.2f}×）")
        if target_growth is not None and p.get("revenue_growth") is not None:
            if p["revenue_growth"] < -0.40:
                reasons.append("收入增速数据异常（同比 <-40%），未计入可比性评分")
            else:
                diff = abs(p["revenue_growth"] - target_growth)
                if diff > 0.10:
                    penalty = min(20.0, (diff - 0.10) * 100)
                    score -= penalty
                    reasons.append(f"收入增速差 {diff:.0%}（-{penalty:.0f}）")
                else:
                    reasons.append(f"收入增速接近（差 {diff:.0%}）")
        if target_margin is not None and p.get("ebit_margin") is not None:
            diff = abs(p["ebit_margin"] - target_margin)
            if diff > 0.10:
                penalty = min(20.0, (diff - 0.10) * 100)
                score -= penalty
                reasons.append(f"EBIT 利润率差 {diff:.0%}（-{penalty:.0f}）")
            else:
                reasons.append(f"EBIT 利润率接近（差 {diff:.0%}）")
        if p.get("industry") and fin.industry:
            same = (p["industry"] == fin.industry or
                    p["industry"] in fin.industry or fin.industry in p["industry"])
            if same:
                reasons.append("同属一个行业")
            else:
                score -= 12
                reasons.append(f"行业为「{p['industry']}」（-12）")
        score = max(20.0, min(100.0, score))
        level = "高" if score >= 75 else "中" if score >= 55 else "低"
        p["comparability"] = {
            "score": round(score, 1),
            "level": level,
            "reasons": reasons,
        }

    for key in chosen:
        if key == "pe_forward" and (asm.forward_net_income is None or asm.forward_net_income <= 0):
            warnings.append("前瞻PE需同年份预测归母净利润，不得与历史净利润混用；本项跳过。")
            continue
        if key == "peg" and (asm.forward_net_income_growth is None or asm.forward_net_income_growth <= 0):
            warnings.append("PEG需预测归母净利润增长率，不能以营收增速代替；本项跳过。")
            continue
        stat = _peer_stat(peers, key)
        if stat["count"] < 2:
            warnings.append(f"{MULTIPLE_LABELS[key]} 同业有效样本不足两家，已跳过。")
            continue
        med = stat["median"]
        user_adjust = (asm.multiple_adjustment or {}).get(key, 0.0)
        if user_adjust:
            adjust, adjust_reason = user_adjust, "使用者指定调整"
        elif asm.peer_growth_adjustment:
            adjust, adjust_reason = _auto_adjustment(key, fin, peers, target_growth)
        else:
            adjust, adjust_reason = 0.0, "未启用自动调整"
        applied = med * (1 + adjust)

        metric_key = _METRIC_KEY[key]
        base = asm.forward_net_income if key == "pe_forward" else m.get(metric_key)
        implied_equity = None
        basis = ""
        if key == "peg":
            growth_pct = asm.forward_net_income_growth * 100
            implied_pe = applied * growth_pct
            if base and base > 0 and implied_pe > 0:
                implied_equity = implied_pe * base
                basis = f"PEG {applied:.2f} × 预期增速 {growth_pct:.1f}% = 隐含 PE {implied_pe:.1f}x × 净利润"
                applied_effective = implied_pe
            else:
                warnings.append("PEG：目标净利润为负或增速缺失，已跳过。")
                continue
        elif key in ("ev_revenue", "ev_ebitda", "ev_ebit"):
            if fin.cash is None or fin.total_debt is None:
                warnings.append(f"{MULTIPLE_LABELS[key]}：净债务不完整，不允许当0处理，已跳过。")
                continue
            if base and base > 0:
                implied_ev = applied * base
                implied_equity = implied_ev - net_debt - (fin.minority_interest or 0) - (fin.preferred_stock or 0)
                basis = f"{MULTIPLE_LABELS[key]} × {metric_key} = 企业价值，再扣净负债/少数股东权益"
                applied_effective = applied
            else:
                warnings.append(f"{MULTIPLE_LABELS[key]}：目标 {metric_key} 为负或缺失，已跳过。")
                continue
        else:
            if base and base > 0:
                implied_equity = applied * base
                basis = f"{MULTIPLE_LABELS[key]} × {metric_key}"
                applied_effective = applied
            else:
                warnings.append(f"{MULTIPLE_LABELS[key]}：目标 {metric_key} 为负或缺失，已跳过。")
                continue

        if implied_equity is None:
            continue
        if implied_equity <= 0:
            warnings.append(f"{MULTIPLE_LABELS[key]}：隐含股权价值不大于0，保留为异常诊断，不纳入估值。")
            continue
        per_share = safe_div(implied_equity, fin.shares_outstanding)
        if per_share is None or per_share <= 0:
            warnings.append(f"{MULTIPLE_LABELS[key]}：股本无效或每股价值不大于0，已跳过。")
            continue
        results.append({
            "multiple": key,
            "label": MULTIPLE_LABELS[key],
            "peer_median": med,
            "peer_mean": stat["mean"],
            "peer_p25": stat["p25"],
            "peer_p75": stat["p75"],
            "peer_min": stat["min"],
            "peer_max": stat["max"],
            "sample_count": stat["count"],
            "dispersion": stat["dispersion"],
            "excluded": stat["excluded"],
            "adjustment": adjust,
            "adjustment_reason": adjust_reason,
            "applied_multiple": applied,
            "applied_multiple_effective": applied_effective,
            "metric_basis": _METRIC_KEY[key],
            "metric_value": base,
            "net_debt_deducted": net_debt if key.startswith("ev_") else 0.0,
            "implied_equity_value": implied_equity,
            "implied_per_share": per_share,
            "category": "enterprise" if key.startswith("ev_") else "equity",
        })

    if not results:
        return {
            "ok": False,
            "error": "所有选用倍数都无法得到有效结果",
            "reason": "目标指标与同业样本组合后无有效结果",
            "decisions": decision_blocks,
            "peer_companies": peer_table,
            "warnings": warnings,
        }

    equities = [r["implied_equity_value"] for r in results]
    per_shares = [r["implied_per_share"] for r in results if r["implied_per_share"] is not None]
    mid = median(equities)
    low, high = min(equities), max(equities)
    target_mult = target_multiples(fin, target_growth)

    # 目标在同业分布中的位置
    positioning = {}
    for key in chosen:
        tval = target_mult.get(key)
        vals = [getattr(p, key) for p in peers if getattr(p, key) is not None and getattr(p, key) > 0]
        if tval is None or not vals:
            continue
        med = median(vals)
        positioning[key] = {
            "label": MULTIPLE_LABELS[key],
            "target": tval,
            "peer_median": med,
            "premium_discount": safe_div(tval, med) - 1 if med else None,
            "percentile": percentile_rank(tval, vals),
            "peer_min": min(vals),
            "peer_max": max(vals),
        }

    # 判断文字（数据驱动，不写死）
    judgment_parts = []
    for key, pos in positioning.items():
        if pos["premium_discount"] is None:
            continue
        pd = pos["premium_discount"]
        direction = "溢价" if pd >= 0 else "折价"
        judgment_parts.append(
            f"{pos['label']} {pos['target']:.2f}x，较同业中位 {pos['peer_median']:.2f}x "
            f"{direction} {abs(pd):.1%}，位于同业 {pos['percentile']:.0f} 分位"
        )
    judgment = "；".join(judgment_parts) if judgment_parts else "目标倍数或同业样本不足，无法给出相对位置判断。"

    # 方法结论的区间
    valuation_range = {
        "low": low,
        "mid": mid,
        "high": high,
        "low_per_share": min(per_shares) if per_shares else None,
        "mid_per_share": median(per_shares) if per_shares else None,
        "high_per_share": max(per_shares) if per_shares else None,
        "basis": "各选用倍数隐含股权价值的最小/中位/最大",
    }

    peer_growth_med = median_of([p.revenue_growth for p in peers
                                 if p.revenue_growth is not None
                                 and -0.40 <= p.revenue_growth <= 1.50])
    if (target_growth is not None and peer_growth_med is not None
            and target_growth - peer_growth_med > 0.20):
        warnings.append(
            f"目标首年增速 {target_growth:.1%} 比同业中位 {peer_growth_med:.1%} 高 "
            f"{(target_growth - peer_growth_med) * 100:.0f}pp，可能偏乐观；"
            "若行业处于下行周期，请下调增速或核对一致预期。"
        )

    if len(results) == 1:
        warnings.append("仅有一个倍数得到有效结果，相对估值的稳健性较低。")
    for key in chosen:
        stat = _peer_stat(peers, key)
        if stat["dispersion"] is not None and stat["dispersion"] > defaults.peer_rules()["dispersion_warn"]:
            warnings.append(
                f"{MULTIPLE_LABELS[key]} 同业离散度（IQR/中位）{stat['dispersion']:.0%} 偏高，"
                "说明样本估值分歧大，中位数的代表性下降。"
            )

    # 所有候选倍数的同业中位数（含未进入结论的参考倍数，供 SOTP 兜底使用）
    peer_multiples = {}
    for block in decision_blocks:
        for d in block.get("decisions") or []:
            key = d.get("multiple")
            if key in peer_multiples:
                continue
            stat = _peer_stat(peers, key)
            peer_multiples[key] = {
                "median": stat["median"], "mean": stat["mean"],
                "p25": stat["p25"], "p75": stat["p75"],
                "count": stat["count"], "dispersion": stat["dispersion"],
                "used": d.get("used", False), "reason": d.get("reason", ""),
            }

    missing_provenance = [p.ticker or p.name for p in peers if not p.source or not p.as_of]
    low_matches = [p["ticker"] for p in peer_table if p["comparability"]["score"] < 55]
    # 缺少来源日期/匹配质量过低，不允许对外给可信的自动综合估值单点。
    review_required = bool(missing_provenance or len(low_matches) >= max(2, (len(peers) + 1) // 2))
    if missing_provenance:
        warnings.append("同业缺少可核验数据来源或估值基准日期：" + ",".join(missing_provenance))
    if low_matches:
        warnings.append("业务可比性低的候选：" + ",".join(low_matches))
    return {
        "ok": True,
        "review_required": review_required,
        "method": "comps",
        "status": "review_required" if review_required else "ok",
        "caliber": "LYR（最近年报）",
        "peer_count": len(peers),
        "peers_used": len(peers),
        "peers_detail": [p.to_dict() for p in peers],
        "peer_companies": peer_table,
        "comparability_note": ("可比性评分综合考虑行业、规模、收入增速、EBIT 利润率；"
                               "75 分以上为高，55–74 为中，55 以下为低。"
                               "评分只用于提示样本质量，不替代人工复核。"),
        "peer_selection": peer_selection or {},
        "peer_multiples": peer_multiples,
        "decisions": decision_blocks,
        "results": results,
        "implied_equity_value": mid,
        "implied_per_share": median(per_shares) if per_shares else None,
        "range_low": low,
        "range_high": high,
        "valuation_range": valuation_range,
        "target_multiples": target_mult,
        "positioning": positioning,
        "judgment": judgment,
        "target_growth": target_growth,
        "warnings": warnings,
    }
