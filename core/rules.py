"""规则层：方法适用性 → 可靠性评分 → 权重 → 交叉验证 → 最终判断。

这一层是 v2 的核心。它解决旧版三个问题：
  1. 缺输入就跳过方法 → 现在由规则补假设、选同业、选指标，并披露；
  2. 三法机械平均 → 现在按可靠性和分歧度动态定权；
  3. DCF 显著偏离市价仍输出「显著低估」→ 现在把市场隐含折现率、
     终值占比、方法分歧作为硬约束写进 gates 和 confidence。
"""
from __future__ import annotations

from statistics import median

from . import defaults
from .metrics import clamp, safe_div, volatility


def _score_level(score: float) -> str:
    if score >= 75:
        return "高"
    if score >= 50:
        return "中"
    return "低"


def dcf_reliability(dcf: dict, asm, fin, market: str = "A") -> dict:
    score = 100.0
    deductions = []
    if not dcf.get("ok"):
        return {"score": 0, "level": "低", "deductions": [{"reason": "DCF 未成功", "points": 100}]}

    diag = dcf.get("diagnostics") or {}
    tv_ratio = diag.get("tv_ratio")
    if tv_ratio is not None:
        if tv_ratio > 0.85:
            score -= 25
            deductions.append({"reason": f"终值占 EV {tv_ratio:.0%}，超过 85%", "points": 25})
        elif tv_ratio > 0.82:
            score -= 5
            deductions.append({"reason": f"终值占 EV {tv_ratio:.0%}，接近 85% 上限", "points": 5})
        elif tv_ratio < 0.45:
            score -= 10
            deductions.append({"reason": f"终值占 EV {tv_ratio:.0%}，低于 45%", "points": 10})
    divergence = diag.get("tv_divergence")
    if divergence is not None and divergence > 0.50:
        score -= 20
        deductions.append({"reason": f"Gordon 与退出倍数终值偏离 {divergence:.0%}，超过 50%", "points": 20})
    elif divergence is not None and divergence > 0.30:
        score -= 15
        deductions.append({"reason": f"Gordon 与退出倍数终值偏离 {divergence:.0%}", "points": 15})
    gap_bp = diag.get("wacc_gap_bp")
    if gap_bp is not None:
        if gap_bp > 300:
            score -= 25
            deductions.append({"reason": f"CAPM 与市场隐含 WACC 相差 {gap_bp:.0f}bp", "points": 25})
        elif gap_bp > 150:
            score -= 15
            deductions.append({"reason": f"CAPM 与市场隐含 WACC 相差 {gap_bp:.0f}bp", "points": 15})
    spread = diag.get("wacc_minus_g")
    if spread is not None and spread < 0.02:
        score -= 20
        deductions.append({"reason": f"WACC−g 仅 {spread:.2%}，终值对折现率极敏感", "points": 20})

    years = len([v for v in (fin.revenue or []) if v is not None])
    if years < 3:
        score -= 15
        deductions.append({"reason": f"收入历史仅 {years} 年", "points": 15})

    ebit = [v for v in (fin.ebit or []) if v is not None]
    if ebit and (min(ebit) < 0 or (volatility(ebit) or 0) > 0.6):
        score -= 15
        deductions.append({"reason": "EBIT 波动大或曾为负，周期/一次性因素未完全正常化", "points": 15})

    # 由规则估算的费率
    for label, value in (("折旧摊销", asm.da_pct_revenue), ("资本开支", asm.capex_pct_revenue),
                         ("营运资本", asm.nwc_pct_revenue)):
        source = getattr(asm, "_assumption_source_" + label, "")
        if value is not None and source.startswith("缺"):
            score -= 6
            deductions.append({"reason": f"{label}费率由规则估算", "points": 6})

    # 行业锚点偏离
    anchor = defaults.sector_anchor(fin.industry or "", "")
    if anchor and dcf.get("wacc") is not None:
        if abs(dcf["wacc"] - anchor["wacc"]) > 0.03:
            score -= 10
            deductions.append({"reason": f"WACC {dcf['wacc']:.2%} 偏离行业锚点 {anchor['wacc']:.2%} 超过 300bp", "points": 10})

    score = max(0.0, min(100.0, score))
    return {"score": round(score, 1), "level": _score_level(score), "deductions": deductions}


def comps_reliability(comps: dict) -> dict:
    score = 100.0
    deductions = []
    if not comps.get("ok"):
        return {"score": 0, "level": "低", "deductions": [{"reason": "Comps 未成功", "points": 100}]}
    n = comps.get("peer_count") or 0
    if n < 3:
        score -= 40 if n <= 1 else 25
        deductions.append({"reason": f"可比公司仅 {n} 家", "points": 40 if n <= 1 else 25})
    elif n == 3:
        score -= 10
        deductions.append({"reason": "可比公司 3 家，样本偏少", "points": 10})

    tier = (comps.get("peer_selection") or {}).get("tier")
    if tier == "dynamic":
        score -= 10
        deductions.append({"reason": "可比公司由同行业动态筛选，非人工复核名单", "points": 10})
    elif tier == "proxy":
        score -= 25
        deductions.append({"reason": "行业未精确匹配，使用板块代理样本", "points": 25})

    results = comps.get("results") or []
    if len(results) == 1:
        score -= 15
        deductions.append({"reason": "仅一个倍数有效", "points": 15})
    elif len(results) == 2:
        score -= 5
        deductions.append({"reason": "仅两个倍数有效", "points": 5})

    max_disp = max([r.get("dispersion") or 0 for r in results] or [0])
    if max_disp > 1.0:
        score -= 25
        deductions.append({"reason": f"同业倍数离散度 {max_disp:.0%} 很高", "points": 25})
    elif max_disp > 0.6:
        score -= 15
        deductions.append({"reason": f"同业倍数离散度 {max_disp:.0%} 偏高", "points": 15})

    bad = sum(1 for p in (comps.get("peer_companies") or []) if not p.get("data_ok", True))
    if bad:
        score -= min(20, bad * 5)
        deductions.append({"reason": f"{bad} 家可比公司数据不完整", "points": min(20, bad * 5)})

    score = max(0.0, min(100.0, score))
    return {"score": round(score, 1), "level": _score_level(score), "deductions": deductions}


def sotp_reliability(sotp: dict) -> dict:
    score = 100.0
    deductions = []
    if not sotp.get("ok"):
        return {"score": 0, "level": "低", "deductions": [{"reason": "SOTP 未成功", "points": 100}]}
    coverage = sotp.get("revenue_coverage")
    if coverage is not None:
        if coverage < 0.60:
            score -= 30
            deductions.append({"reason": f"分部收入覆盖仅 {coverage:.0%}", "points": 30})
        elif coverage < 0.80:
            score -= 20
            deductions.append({"reason": f"分部收入覆盖 {coverage:.0%}", "points": 20})
    n = sotp.get("segment_count") or 0
    if n <= 1:
        score -= 30
        deductions.append({"reason": "仅一个分部，SOTP 等同整体估值", "points": 30})
    elif n == 2:
        score -= 15
        deductions.append({"reason": "仅两个分部，SOTP 对整体估值的解释力有限", "points": 15})
    elif n > 6:
        score -= 5
        deductions.append({"reason": f"分部 {n} 个，样本较碎", "points": 5})

    rows = sotp.get("rows") or []
    if rows and all(r.get("metric") == "revenue" for r in rows):
        score -= 10
        deductions.append({"reason": "分部仅有收入口径，EBIT/EBITDA 靠分摊", "points": 10})
    if sotp.get("corporate_cost_estimated"):
        score -= 5
        deductions.append({"reason": "总部费用为规则估算", "points": 5})

    fallback = sum(1 for r in rows if r.get("note") and "兜底" in str(r.get("note")))
    if fallback:
        score -= min(20, fallback * 8)
        deductions.append({"reason": f"{fallback} 个分部使用兜底倍数", "points": min(20, fallback * 8)})

    score = max(0.0, min(100.0, score))
    return {"score": round(score, 1), "level": _score_level(score), "deductions": deductions}


def ddm_reliability(ddm: dict) -> dict:
    score = 100.0
    deductions = []
    if not ddm.get("ok"):
        return {"score": 0, "level": "低", "deductions": [{"reason": "DDM 未成功", "points": 100}]}
    if (ddm.get("payout_source") or "").startswith("缺"):
        score -= 10
        deductions.append({"reason": "分红率为规则估算", "points": 10})
    if ddm.get("ddm_value") and ddm.get("ri_value"):
        gap = abs(ddm["ddm_value"] - ddm["ri_value"]) / max(ddm["ddm_value"], ddm["ri_value"])
        if gap > 0.35:
            score -= 15
            deductions.append({"reason": f"DDM 与剩余收益相差 {gap:.0%}", "points": 15})
    spread = (ddm.get("cost_of_equity") or 0) - (ddm.get("growth") or 0)
    if spread < 0.02:
        score -= 20
        deductions.append({"reason": f"Ke−g 仅 {spread:.2%}", "points": 20})
    score = max(0.0, min(100.0, score))
    return {"score": round(score, 1), "level": _score_level(score), "deductions": deductions}


def _method_value(result: dict, key: str) -> float | None:
    if key == "comps":
        return result.get("implied_per_share")
    if key == "ddm":
        return result.get("per_share")
    return result.get("per_share")


def resolve_weights(method_values: dict[str, float | None],
                    reliabilities: dict[str, dict],
                    method_selection: str = "auto",
                    user_weights: dict[str, float] | None = None,
                    weight_mode: str = "rules",
                    has_sotp: bool = False,
                    is_financial: bool = False) -> dict:
    """决定各方法权重。返回 weights / trace / source / divergence。"""
    keys = [k for k, v in method_values.items() if v is not None and v > 0]
    usable = {k: method_values[k] for k in keys}
    trace = []

    if not usable:
        return {"ok": False, "weights": {}, "trace": [], "source": "没有可用方法",
                "divergence": None, "confidence": "低"}

    # 1) 单一方法选择
    single = (method_selection or "").lower()
    if single in usable and single in ("dcf", "comps", "sotp", "ddm"):
        weights = {k: (1.0 if k == single else 0.0) for k in usable}
        trace.append({"rule": "使用者选择单一方法", "method": single, "weight": 1.0})
        return {
            "ok": True,
            "weights": weights,
            "trace": trace,
            "source": f"使用者选择仅 {single.upper()}",
            "divergence": None,
            "confidence": reliabilities.get(single, {}).get("level", "中"),
            "primary": single,
        }

    # 2) 手工权重
    if user_weights and weight_mode == "manual":
        total = sum(v for k, v in user_weights.items() if k in usable and v > 0)
        if total > 0:
            weights = {k: (user_weights.get(k, 0.0) / total if k in usable else 0.0) for k in usable}
            for k in usable:
                trace.append({"rule": "使用者手工权重（已归一化）", "method": k, "weight": round(weights[k], 4)})
                if reliabilities.get(k, {}).get("score", 100) < 40:
                    trace.append({"rule": "提示：该方法可靠性低，但使用者选择保留", "method": k,
                                  "reliability": reliabilities[k]["score"]})
            return {
                "ok": True, "weights": weights, "trace": trace,
                "source": "使用者手工权重（已归一化）", "divergence": None,
                "confidence": _weighted_confidence(weights, reliabilities),
                "primary": max(weights, key=weights.get),
            }

    # 3) 默认权重
    if is_financial:
        base = {"ddm": 0.5, "comps": 0.5}
    elif has_sotp:
        base = {"dcf": 0.40, "comps": 0.30, "sotp": 0.30}
    else:
        base = {"dcf": 0.50, "comps": 0.50}
    base = {k: v for k, v in base.items() if k in usable}
    if not base:
        # 选中的方法组合不在默认表里，等权
        base = {k: 1.0 / len(usable) for k in usable}
        base_source = "默认权重：可用方法等权"
    else:
        base_source = ("默认权重：金融行业 DDM 50% / Comps 50%" if is_financial
                       else ("默认权重：有分部 DCF 40% / Comps 30% / SOTP 30%" if has_sotp
                             else "默认权重：DCF 50% / Comps 50%"))

    # 4) 可靠性调整
    adjusted = {}
    for k in usable:
        rel = reliabilities.get(k, {}).get("score", 50)
        bw = base.get(k, 0.0)
        if bw == 0:
            adjusted[k] = 0.0
            continue
        if rel >= 75:
            mult = 1.10
        elif rel >= 50:
            mult = 1.00
        elif rel >= 40:
            mult = 0.65
        else:
            mult = 0.25
        adjusted[k] = bw * mult
        trace.append({"rule": f"可靠性 {rel:.0f} 分 → 权重乘数 {mult:.2f}",
                      "method": k, "base_weight": bw, "weight": round(bw * mult, 4)})

    # 5) 方法分歧处理
    ranked = sorted(usable.items(), key=lambda kv: kv[1], reverse=True)
    divergence = None
    primary = ranked[0][0]
    if len(ranked) >= 2:
        hi, lo = ranked[0][1], ranked[-1][1]
        if lo > 0:
            divergence = hi / lo - 1
    if divergence is not None and divergence > 0.50:
        # 以可靠性更高者为主，而不是机械平均
        primary = max(usable, key=lambda k: (reliabilities.get(k, {}).get("score", 0), usable[k]))
        strong = divergence > 1.00
        main_w = 0.80 if strong else 0.70
        adjusted = {k: 0.0 for k in usable}
        adjusted[primary] = main_w
        rest = [k for k in usable if k != primary]
        if rest:
            sub_total = sum(max(reliabilities.get(k, {}).get("score", 50), 1) for k in rest)
            for k in rest:
                adjusted[k] = (1 - main_w) * max(reliabilities.get(k, {}).get("score", 50), 1) / sub_total
        trace.append({
            "rule": (f"方法间分歧 {divergence:.0%}，规则改为以 {primary} 为主"
                     f"（{main_w:.0%}），其余方法降为参考"),
            "method": primary,
            "weight": main_w,
            "divergence": divergence,
        })
    elif divergence is not None and divergence > 0.30:
        trace.append({"rule": f"方法间分歧 {divergence:.0%}，提示但不改权重", "divergence": divergence})

    total = sum(adjusted.values())
    if total <= 0:
        adjusted = {k: 1.0 / len(usable) for k in usable}
        total = 1.0
    weights = {k: round(v / total, 4) for k, v in adjusted.items()}

    confidence = _weighted_confidence(weights, reliabilities)
    if divergence is not None and divergence > 1.0:
        confidence = "低"

    source = base_source + "；已按各方法可靠性调整"
    if divergence is not None and divergence > 0.50:
        main_w = weights.get(primary, 0.0)
        source += (f"；方法分歧 {divergence:.0%}，改以可靠性更高的 {primary} 为主"
                   f"（{main_w:.0%}），其余方法降为参考")
    return {
        "ok": True,
        "weights": weights,
        "trace": trace,
        "source": source,
        "divergence": divergence,
        "confidence": confidence,
        "primary": primary,
    }


def _weighted_confidence(weights: dict, reliabilities: dict) -> str:
    total = sum(w for w in weights.values() if w > 0) or 1
    score = sum(w * reliabilities.get(k, {}).get("score", 50) for k, w in weights.items()) / total
    return _score_level(score)


def cross_validate(dcf: dict, comps: dict, sotp: dict, ddm: dict,
                   fin, asm, weights: dict) -> list[dict]:
    """输出 gates：每条带 severity / code / message / affected_paths。"""
    gates = []

    def add(code, severity, message, paths=None):
        gates.append({"code": code, "severity": severity, "message": message,
                      "affected_paths": paths or []})

    if dcf.get("ok"):
        diag = dcf.get("diagnostics") or {}
        tv = diag.get("tv_ratio")
        if tv is not None and tv > 0.85:
            add("TV_RATIO_HIGH", "warn", f"终值占企业价值 {tv:.0%}，超过 85%，DCF 实质依赖远期假设。",
                ["dcf.tv_ratio"])
        if (diag.get("tv_divergence") or 0) > 0.30:
            add("TV_METHOD_DIVERGENCE", "warn",
                f"Gordon 与退出倍数终值相差 {diag['tv_divergence']:.0%}，已取中点。",
                ["dcf.tv_base"])
        gap = diag.get("wacc_gap_bp")
        if gap and gap > 150:
            add("WACC_IMPLIED_GAP", "warn" if gap <= 300 else "block",
                f"CAPM 与市场隐含 WACC 相差 {gap:.0f}bp，折现率假设与市场定价存在分歧。",
                ["dcf.wacc", "valuation.blended"])
        if (diag.get("wacc_minus_g") or 1) < 0.02:
            add("WACC_G_SPREAD", "warn", "WACC−g 小于 2%，终值对两个假设都极敏感。",
                ["dcf.tv_base"])

    if weights:
        values = {}
        if dcf.get("ok") and dcf.get("per_share") is not None:
            values["dcf"] = dcf["per_share"]
        if comps.get("ok") and comps.get("implied_per_share") is not None:
            values["comps"] = comps["implied_per_share"]
        if sotp.get("ok") and sotp.get("per_share") is not None:
            values["sotp"] = sotp["per_share"]
        if ddm.get("ok") and ddm.get("per_share") is not None:
            values["ddm"] = ddm["per_share"]
        if len(values) >= 2:
            hi, lo = max(values.values()), min(values.values())
            if lo > 0:
                divergence = hi / lo - 1
                if divergence > 0.50:
                    add("METHOD_DIVERGENCE", "warn" if divergence <= 1.0 else "block",
                        f"方法间估值分歧 {divergence:.0%}，加权平均的参考价值有限；"
                        "规则已按可靠性确定主方法并降低其余权重。",
                        ["valuation.blended"])

    if not (fin.market_cap and fin.shares_outstanding):
        add("NO_MARKET_PRICE", "block", "未取得股价/股本，无法计算每股价值与上行空间。",
            ["valuation.market_data", "valuation.blended"])
    if not fin.price:
        add("NO_PRICE", "warn", "未取得实时股价，估值结论缺少市场锚。", ["valuation.market_data"])
    if any("股本按腾讯财经总市值" in str(note) for note in (fin.data_notes or [])):
        add("SHARES_ESTIMATED", "warn",
            "东方财富行情受限时，使用腾讯财经总市值/股价反推股本；这是近似值，"
            "每股估值与上行空间须以交易所或公司披露的准确股本复核。",
            ["valuation.market_data.shares_outstanding", "valuation.blended"])

    # 三情景单调性
    return gates


def verdict_from_upside(upside: float | None) -> str:
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


def next_questions(fin, company, gate: dict, assumed: bool = True) -> list[dict]:
    """交互式对话框要问的问题。即使使用者不回答，规则也会给默认值。"""
    questions = []
    if not fin.revenue:
        questions.append({"key": "financials.revenue", "question": "请补充近 3 年营业收入（元）。",
                          "default": None, "required": True, "why": "没有收入历史无法建立预测。"})
    if not fin.total_debt and not fin.cash:
        questions.append({"key": "financials.total_debt/cash", "question": "请补充最新有息负债与货币资金。",
                          "default": "按 0 处理", "required": False,
                          "why": "用于企业价值到股权价值的桥接；缺失时按 0 处理并提示。"})
    questions.append({
        "key": "assumptions.revenue_growth_y1",
        "question": "首年收入增速用多少？",
        "default": None,
        "default_rule": "近 3/5 年 CAGR 与最近一年同比加权",
        "required": False,
        "why": "增速是 DCF 最敏感的假设之一；不回答则按规则合成。",
    })
    questions.append({
        "key": "assumptions.ebit_margin",
        "question": "预测期 EBIT 利润率用多少？",
        "default": None,
        "default_rule": "近三年 EBIT/收入中位数",
        "required": False,
        "why": "利润率决定现金流的水平；不回答则用历史中位数。",
    })
    questions.append({
        "key": "assumptions.wacc_mode",
        "question": "折现率口径？",
        "default": "reconciled",
        "options": ["capm（纯 CAPM）", "reconciled（与市场隐含折现率校准）", "manual（手工指定）"],
        "required": False,
        "why": "CAPM 在低利率环境下常低于市场隐含折现率，纯 CAPM 会系统性高估。",
    })
    if gate.get("support") != "supported":
        questions.append({
            "key": "method_selection_industry",
            "question": f"该行业标准 DCF 不适用：{gate.get('reason')} 是否改用 {gate.get('primary_absolute') or 'Comps'}？",
            "default": gate.get("primary_absolute") or "comps",
            "required": False,
            "why": "行业结构性限制，不是数据缺失。",
        })
    questions.append({
        "key": "peers",
        "question": "可比公司用系统推荐，还是你指定名单？",
        "default": "系统推荐",
        "default_rule": "同行业、商业模式相近、规模/增速/利润率可比，4–6 家",
        "required": False,
        "why": "不指定时按行业池自动选，并逐家披露选取理由。",
    })
    questions.append({
        "key": "method_selection",
        "question": "估值方法：只做 DCF / 只做 Comps / 只做 SOTP / 综合？",
        "default": "auto（全部适用方法 + 规则融合）",
        "options": ["dcf", "comps", "sotp", "auto"],
        "required": False,
        "why": "选择单一方法时仍会给出交叉校验；选择综合时按规则定权。",
    })
    return questions
