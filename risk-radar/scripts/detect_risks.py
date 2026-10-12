#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
risk-radar / detect_risks.py
============================
B 模块第 2 段：财务风险识别引擎。

输入 : financial-diagnosis 的 ratios 输出（含 evidence 原始值与出处）+ risk_rules.json
输出 : 统一接口里的 data.risks（风险清单 + 证据链 + 待核验队列）

设计原则
--------
1. 规则外置：所有触发条件写在 risk_rules.json 里，改规则不改代码。
2. 安全求值：触发表达式用受限的 AST 解释器执行（白名单运算符 + 白名单函数），
   绝不使用 eval / exec，避免规则文件被注入时执行任意代码。
3. 不静默判安全：任何输入缺失 → status = not_evaluable → 进 review_queue，
   绝不因为"算不出来"就当成"没问题"。
4. 每条风险自带证据链：数据 → 计算 → 年报页码 → 判断 → 归因 → 建议，
   E 的前端可以直接按层展开，不需要再回头查任何东西。

用法
----
    python detect_risks.py --ratios ../financial-diagnosis/demo/output_ratios.json \
                           --rules  ../risk-radar/risk_rules.json \
                           --output demo/output_risks.json --pretty
"""

from __future__ import annotations

import argparse
import ast
import json
import operator as op
import os
from datetime import datetime, timezone, timedelta

SCHEMA_VERSION = "finradar.risk/1.0"

# --------------------------------------------------------------------------- #
# 受限表达式求值器（不用 eval）
# --------------------------------------------------------------------------- #
_ALLOWED_BINOPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
                   ast.Div: op.truediv, ast.Pow: op.pow, ast.Mod: op.mod}
_ALLOWED_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg}
_ALLOWED_CMP = {ast.Gt: op.gt, ast.GtE: op.ge, ast.Lt: op.lt,
                ast.LtE: op.le, ast.Eq: op.eq, ast.NotEq: op.ne}
_ALLOWED_FUNCS = {"abs": abs, "min": min, "max": max, "round": round, "float": float}


class MissingVar(Exception):
    """表达式引用了缺失或为 None 的变量 —— 对应 status = not_evaluable。"""

    def __init__(self, name):
        self.name = name
        super().__init__(name)


class UnsafeExpr(Exception):
    pass


def _eval(node, ctx):
    if isinstance(node, ast.Expression):
        return _eval(node.body, ctx)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float, str)):
            raise UnsafeExpr(f"不支持的常量类型: {type(node.value).__name__}")
        return node.value

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_FUNCS:
            raise UnsafeExpr("函数必须被直接调用")
        if node.id not in ctx or ctx[node.id] is None:
            raise MissingVar(node.id)
        return ctx[node.id]

    if isinstance(node, ast.BinOp):
        if type(node.op) not in _ALLOWED_BINOPS:
            raise UnsafeExpr(f"不支持的运算符: {type(node.op).__name__}")
        return _ALLOWED_BINOPS[type(node.op)](_eval(node.left, ctx), _eval(node.right, ctx))

    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _ALLOWED_UNARY:
            raise UnsafeExpr(f"不支持的一元运算符: {type(node.op).__name__}")
        return _ALLOWED_UNARY[type(node.op)](_eval(node.operand, ctx))

    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx)
        for comparator, right_node in zip(node.ops, node.comparators):
            if type(comparator) not in _ALLOWED_CMP:
                raise UnsafeExpr(f"不支持的比较符: {type(comparator).__name__}")
            right = _eval(right_node, ctx)
            if not _ALLOWED_CMP[type(comparator)](left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BoolOp):
        # 显式短路：and 遇到 False、or 遇到 True 时不再求值右侧，
        # 避免无关变量的缺失把本可判定的规则拖成 not_evaluable
        is_and = isinstance(node.op, ast.And)
        for i, v in enumerate(node.values):
            val = _eval(v, ctx)
            if is_and and not val:
                return False
            if (not is_and) and val:
                return True
        return bool(is_and)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise UnsafeExpr("不允许的函数调用")
        if node.keywords:
            raise UnsafeExpr("不支持关键字参数")
        args = [_eval(a, ctx) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)

    raise UnsafeExpr(f"不支持的表达式节点: {type(node).__name__}")


def eval_expr(expr: str, ctx: dict):
    """返回 (ok, value_or_None, missing_vars)。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise UnsafeExpr(f"表达式语法错误 [{expr}]: {e}")
    try:
        return True, _eval(tree, ctx), None
    except MissingVar as e:
        return False, None, e.name


def vars_in(expr: str) -> list[str]:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return []
    names, out = set(), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            names.add(n.id)
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in names and n.id not in out:
            out.append(n.id)
    return [n for n in out if n not in _ALLOWED_FUNCS]


# --------------------------------------------------------------------------- #
# 变量上下文
# --------------------------------------------------------------------------- #
YI = 1e8

RATE_NAME_PATTERNS = (
    "growth", "margin", "ratio", "roe", "roa", "roic", "gap", "scissors",
    "_effect", "tax_rate", "dependency", "payout", "to_assets", "to_equity",
    "to_revenue", "to_short_term_debt", "to_deposit", "to_income", "to_loan",
    # 银行业专属比率：命中后自动派生 _pp（百分点）变量供解释模板使用
    "nim", "spread", "coverage", "adequacy", "provision", "npl", "_share",
)
RATE_UNITS = ("ratio", "%", "percent", "百分比")

MONEY_NAMES = {
    "gross_profit", "ebit", "ebitda", "nopat", "interest_bearing_debt",
    "short_term_interest_bearing_debt", "net_debt", "invested_capital",
    "working_capital", "ar_total", "fcf", "period_expense", "free_cash_flow",
    "ocf", "capex",
}


def is_rate(name: str, unit: str | None) -> bool:
    """判定该指标是否为「比率」——是则派生 _pp（百分点）变量供解释文案使用。
    三条线索任一命中即可：单位、字段名、展示单位。"""
    if unit in RATE_UNITS:
        return True
    return any(p in name for p in RATE_NAME_PATTERNS)


def build_ctx(diag: dict, meta_extra: dict | None = None) -> tuple[dict, set]:
    ctx: dict = {}
    rates: set = set()

    periods = diag.get("period", {}).get("all") or []
    cur = diag.get("period", {}).get("current")
    prev = diag.get("period", {}).get("previous")

    # ---- 1. 摊平 ratios ---- #
    for cat, items in (diag.get("ratios") or {}).items():
        for k, e in items.items():
            val, prv, unit = e.get("value"), e.get("prev"), e.get("unit")
            ctx[k] = val
            ctx[k + "_prev"] = prv
            ctx[k + "_delta"] = e.get("delta")
            if is_rate(k, unit):
                rates.add(k)
                if val is not None:
                    ctx[k + "_pp"] = val * 100
                if prv is not None:
                    ctx[k + "_prev_pp"] = prv * 100
                dl = e.get("delta")
                if dl is not None:
                    ctx[k + "_delta_pp"] = dl * 100
                    # 基点（BP）：比率类变动在银行/利率语境下常用 BP 表述，
                    # 只给 _delta_pp 会在小于 1pp 时被四舍五入成 0，造成"同比 0BP"的假象
                    ctx[k + "_delta_bp"] = dl * 10000
            if unit == "CNY" or k in MONEY_NAMES:
                if val is not None:
                    ctx[k + "_yi"] = val / YI
                if prv is not None:
                    ctx[k + "_prev_yi"] = prv / YI

    # ---- 2. 摊平 derived（EBIT / NOPAT / 有息负债等） ---- #
    derived = diag.get("derived") or {}
    if cur and isinstance(derived.get(cur), dict):
        for k, v in derived[cur].items():
            ctx.setdefault(k, v)
            if k in MONEY_NAMES or "debt" in k or "capital" in k:
                if v is not None:
                    ctx[k + "_yi"] = v / YI
    if prev and isinstance(derived.get(prev), dict):
        for k, v in derived[prev].items():
            if v is not None:
                ctx.setdefault(k + "_prev", v)
            if (k in MONEY_NAMES or "debt" in k) and v is not None:
                ctx[k + "_prev_yi"] = v / YI

    # ---- 3. 原始抽取值（raw_ 前缀，单位：元） ---- #
    evidence = diag.get("evidence") or {}
    for key, per_pd in evidence.items():
        if cur and isinstance(per_pd.get(cur), dict):
            ctx["raw_" + key] = per_pd[cur].get("value")
        if prev and isinstance(per_pd.get(prev), dict):
            ctx["raw_" + key + "_prev"] = per_pd[prev].get("value")
    for k in list(ctx.keys()):
        if k.startswith("raw_") and isinstance(ctx[k], (int, float)):
            bare = k[4:]
            # 同时提供两种写法：raw_x_yi 与 x_yi，方便规则模板按语义选用
            ctx[bare + "_yi"] = ctx[k] / YI
            ctx["raw_" + bare + "_yi"] = ctx[k] / YI
            if bare.endswith("_prev"):
                ctx[bare[:-5] + "_prev_yi"] = ctx[k] / YI

    # ---- 4. 归因结果（杜邦三段 + 现金流桥） ---- #
    attr = diag.get("attribution") or {}
    dup = attr.get("dupont") or {}
    for grp in ("current", "previous", "contribution"):
        for k, v in (dup.get(grp) or {}).items():
            if grp == "previous":
                ctx.setdefault(k + "_prev", v)
            else:
                ctx[k] = v
            if any(p in k for p in ("margin", "roe", "effect", "turnover")):
                rates.add(k)
                if v is not None:
                    suffix = "_pp" if grp != "previous" else "_prev_pp"
                    ctx[k + suffix] = v * 100
    cb = attr.get("cash_flow_bridge") or {}
    if cb.get("gap") is not None:
        ctx["cash_gap_yi"] = cb["gap"] / YI

    # ---- 5. 公司与假设 ---- #
    assumptions = diag.get("assumptions") or {}
    if assumptions.get("wacc") is not None:
        ctx["wacc"] = float(assumptions["wacc"])
    company = diag.get("company") or {}
    for k in ("name", "ticker", "industry"):
        ctx[k] = company.get(k)

    meta = dict(diag.get("meta") or {})
    meta.update(meta_extra or {})
    audit = meta.get("audit_opinion")
    ctx["audit_opinion"] = audit
    if audit is None:
        ctx["audit_opinion_flag"] = None
    else:
        ctx["audit_opinion_flag"] = 0 if ("标准无保留" in str(audit)) else 1
    bm = meta.get("industry_gross_margin_benchmark")
    ctx["industry_gross_margin_benchmark"] = float(bm) if bm is not None else None

    return ctx, rates


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def detect(diag: dict, rules_doc: dict, meta_extra: dict | None = None,
           profile: dict | None = None) -> dict:
    ctx, _ = build_ctx(diag, meta_extra)

    profile = profile or {}
    na_metrics = set((profile.get("metric_applicability") or {}).get("not_applicable") or [])
    overrides = profile.get("rule_overrides") or {}
    extra_rules = profile.get("extra_rules") or []
    profile_derived = profile.get("derived_vars") or {}

    # ---- 派生变量：通用 + 行业剖面 ---- #
    derived_spec = dict(rules_doc.get("derived_vars") or {})
    derived_spec.update(profile_derived)
    for name, expr in derived_spec.items():
        if name.startswith("_"):
            continue
        ok, val, missing = eval_expr(expr, ctx)
        ctx[name] = val if ok else None
        if ok and any(p in name for p in RATE_NAME_PATTERNS):
            ctx[name + "_pp"] = val * 100
        if ok and isinstance(val, (int, float)) and name in na_metrics:
            pass

    # ---- 行业剖面：注册额外类别标签 ---- #
    categories = dict(rules_doc.get("categories") or {})
    categories.update(profile.get("categories") or {})

    # ---- 行业剖面：把基准分位数注入 ctx，供规则与模板使用 ---- #
    bmk = (profile.get("benchmarks") or {}).get("values") or {}
    for name, spec in bmk.items():
        if not isinstance(spec, dict):
            continue
        for q in ("p10", "p25", "median", "p75", "p90"):
            v = spec.get(q)
            if isinstance(v, (int, float)):
                ctx[f"{name}_industry_{q}"] = float(v)
                ctx[f"{name}_industry_{q}_pp"] = float(v) * 100

    severity_scale = rules_doc.get("severity_scale") or {}
    cur = diag.get("period", {}).get("current")
    prev = diag.get("period", {}).get("previous")

    risks, review_queue = [], []
    counts = {"triggered": 0, "passed": 0, "not_evaluable": 0, "not_applicable": 0,
              "high": 0, "medium": 0, "low": 0}
    cat_stat: dict[str, dict] = {}
    na_reasons: list[dict] = []

    def resolve(rule: dict) -> tuple[dict, str | None]:
        """返回 (生效规则, 不适用原因 or None)。"""
        ov = overrides.get(rule["risk_id"])
        if ov:
            action = ov.get("action", "keep")
            if action == "disable":
                return rule, ov.get("reason") or "行业剖面判定本规则不适用"
            if action == "modify":
                merged = dict(rule)
                for k, v in ov.items():
                    if k in ("action", "reason"):
                        continue
                    merged[k] = v
                return merged, None
        # 未显式覆盖：若触发表达式引用的指标全部落在本行业不适用清单里，判为不适用
        used = [v for v in vars_in(rule.get("trigger", ""))]
        core = [v for v in used if not v.endswith("_prev") and not v.endswith("_delta")]
        if core and na_metrics and all(v in na_metrics for v in core):
            return rule, ("触发指标 " + ", ".join(core) + " 在本行业口径下不适用")
        return rule, None

    effective = list(rules_doc.get("rules", [])) + list(extra_rules)

    for rule in effective:
        rid = rule["risk_id"]
        cat = rule.get("category", "other")
        cat_stat.setdefault(cat, {"triggered": 0, "high": 0, "medium": 0, "low": 0})

        rule, na_reason = resolve(rule)
        if na_reason:
            counts["not_applicable"] += 1
            na_reasons.append({"risk_id": rid, "risk_name": rule.get("risk_name"),
                               "reason": na_reason})
            risks.append({
                "risk_id": rid,
                "risk_name": rule.get("risk_name"),
                "risk_name_en": rule.get("risk_name_en"),
                "category": cat,
                "category_label": categories.get(cat),
                "status": "not_applicable",
                "severity": None,
                "severity_tag": None,
                "score": None,
                "trigger": rule.get("trigger"),
                "trigger_display": rule.get("trigger_display"),
                "threshold": rule.get("threshold"),
                "evidence_required": rule.get("evidence_required", []),
                "confidence": rule.get("confidence"),
                "explanation": f"本行业（{profile.get('label', '未识别')}）不适用：{na_reason}",
                "evidence_chain": [],
                "trigger_values": {},
            })
            continue

        ok, fired, missing = eval_expr(rule["trigger"], ctx)

        if not ok:
            status = "not_evaluable"
            severity, score = None, None
        else:
            status = "triggered" if fired else "passed"
            if fired:
                severity = rule.get("severity", "medium")
                if rule.get("escalate_when"):
                    ok2, esc, _ = eval_expr(rule["escalate_when"], ctx)
                    if ok2 and esc and rule.get("escalate_to"):
                        severity = rule["escalate_to"]
                score = float((severity_scale.get(severity) or {}).get("score_base", 60))
            else:
                severity, score = None, None

        counts[status] += 1
        if status == "triggered":
            counts[severity] += 1
            cat_stat[cat]["triggered"] += 1
            cat_stat[cat][severity] += 1

        item = {
            "risk_id": rid,
            "risk_name": rule.get("risk_name"),
            "risk_name_en": rule.get("risk_name_en"),
            "category": cat,
            "category_label": categories.get(cat),
            "status": status,
            "severity": severity,
            "severity_tag": (severity_scale.get(severity) or {}).get("tag") if severity else None,
            "score": score,
            "trigger": rule.get("trigger"),
            "trigger_display": rule.get("trigger_display"),
            "threshold": rule.get("threshold"),
            "evidence_required": rule.get("evidence_required", []),
            "confidence": rule.get("confidence"),
        }

        if status == "triggered":
            item["explanation"] = _render(rule.get("explanation_template", ""), ctx)
            item["suggestions"] = list(rule.get("suggestions", []))
            item["evidence_chain"] = _evidence_chain(rule, ctx, diag, cur, prev)
            item["trigger_values"] = {
                v: ctx.get(v) for v in vars_in(rule["trigger"]) if v in ctx
            }
        elif status == "passed":
            item["explanation"] = "规则已执行，条件不成立，本项无异常。"
            item["evidence_chain"] = []
            item["trigger_values"] = {
                v: ctx.get(v) for v in vars_in(rule["trigger"]) if v in ctx
            }
        else:
            item["explanation"] = (
                f"无法判定：表达式引用的变量缺失（{missing}），已转人工核验，"
                "不做'无风险'假设。"
            )
            item["evidence_chain"] = []
            item["trigger_values"] = {}
            review_queue.append({
                "type": "risk_not_evaluable",
                "item": f"{rid} {rule.get('risk_name')}",
                "reason": f"缺失变量：{missing}",
                "missing_inputs": [missing] if missing else [],
                "severity_if_triggered": rule.get("severity"),
                "suggested_action": (
                    rule.get("suggestions", [""])[-1]
                    if rule.get("suggestions") else "补充抽取该字段后重算"
                ),
                "needs_human_judgement": True,
            })

        risks.append(item)

    # ---- 待核验队列：继承 diagnosis 的 ---- #
    for q in (diag.get("review_queue") or []):
        review_queue.append(dict(q, inherited_from="financial-diagnosis"))

    # ---- 综合风险评分 ---- #
    raw_score = counts["high"] * 10 + counts["medium"] * 4 + counts["low"] * 1.5
    overall = round(100 * raw_score / (raw_score + 40), 1) if raw_score > 0 else 0.0
    level_cfg = (rules_doc.get("overall_scoring") or {}).get("levels", [])
    level, action = "低", ""
    for lv in sorted(level_cfg, key=lambda x: -x.get("min", 0)):
        if overall >= lv["min"]:
            level, action = lv["level"], lv.get("action", "")
            break

    top = sorted([r for r in risks if r["status"] == "triggered"],
                 key=lambda r: (-r["score"], r["risk_id"]))[:5]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "generator": "risk-radar/scripts/detect_risks.py",
        "rules_version": rules_doc.get("schema_version"),
        "company": diag.get("company", {}),
        "period": diag.get("period", {}),
        "industry_profile": {
            "profile_id": profile.get("profile_id", "manufacturing"),
            "label": profile.get("label", "制造业（通用档，默认剖面）"),
            "statement_model": profile.get("statement_model", "general"),
            "resolved_from": profile.get("_resolved_from", "default"),
            "benchmarks_calibrated": bool((profile.get("benchmarks") or {}).get("calibrated")),
            "metrics_marked_not_applicable": sorted(na_metrics),
            "rules_disabled_or_skipped": len(na_reasons),
            "extra_rules_added": len(extra_rules),
            "not_applicable_detail": na_reasons,
            "regulatory_basis": profile.get("regulatory_basis"),
        },
        "summary": {
            "total_rules": len(risks),
            "in_scope_rules": len(risks) - counts["not_applicable"],
            "triggered": counts["triggered"],
            "passed": counts["passed"],
            "not_evaluable": counts["not_evaluable"],
            "not_applicable": counts["not_applicable"],
            "by_severity": {"high": counts["high"], "medium": counts["medium"], "low": counts["low"]},
            "by_category": cat_stat,
            "overall_risk_score": overall,
            "overall_risk_level": level,
            "suggested_action": action,
            "top_risks": [{"risk_id": r["risk_id"], "risk_name": r["risk_name"],
                           "severity": r["severity"], "severity_tag": r["severity_tag"],
                           "score": r["score"]} for r in top],
        },
        "risks": risks,
        "review_queue": review_queue,
    }


# --------------------------------------------------------------------------- #
# 证据链 / 模板渲染
# --------------------------------------------------------------------------- #
def _render(tpl: str, ctx: dict) -> str:
    if not tpl:
        return ""
    try:
        return tpl.format(**ctx)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        # 模板引用了缺失变量：降级为"变量占位"文本，并显式标注，绝不静默编造
        return tpl + f"（模板变量 {e} 缺失，本句需人工补全）"


def _evidence_chain(rule: dict, ctx: dict, diag: dict, cur, prev):
    """E 前端展开顺序：数据 → 计算 → 年报页码 → 判断 → 归因 → 建议。"""
    ev = diag.get("evidence") or {}
    chain = []

    # 1) 数据：直接落到年报的字段、数值、页码
    for field in rule.get("evidence_required", []):
        node = ev.get(field) or {}
        c = node.get(cur) or {}
        p = node.get(prev) or {}
        chain.append({
            "step": "数据",
            "item": field,
            "value": c.get("display_value"),
            "unit": c.get("display_unit") or c.get("unit"),
            "value_cny": c.get("value"),
            "prev_value": p.get("display_value"),
            "prev_value_cny": p.get("value"),
            "source": c.get("source"),
            "page": c.get("page"),
        })

    # 2) 计算：触发表达式中实际用到的指标
    used = [v for v in vars_in(rule["trigger"]) if v in ctx and ctx[v] is not None]
    chain.append({
        "step": "计算",
        "item": "触发表达式",
        "formula": rule.get("trigger"),
        "values": {v: ctx[v] for v in used},
    })

    # 3) 出处：本条规则涉及的年报页码汇总
    pages, srcs = set(), set()
    for field in rule.get("evidence_required", []):
        for pd in (cur, prev):
            n = (ev.get(field) or {}).get(pd) or {}
            if n.get("page") is not None:
                pages.add(n["page"])
            if n.get("source"):
                srcs.add(n["source"])
    chain.append({
        "step": "出处",
        "item": "年报来源与页码",
        "sources": sorted(srcs),
        "pages": sorted(pages),
    })

    # 4) 判断
    chain.append({
        "step": "判断",
        "item": rule.get("trigger_display"),
        "result": "触发",
        "severity": rule.get("severity"),
    })

    # 5) 归因：把已有的归因结论挂上来
    attr = diag.get("attribution") or {}
    opb = attr.get("operating_profit_bridge") or {}
    cfb = attr.get("cash_flow_bridge") or {}
    chain.append({
        "step": "归因",
        "item": "指标变动归因",
        "unit_note": "金额类字段单位为亿元（由元换算），比率类字段为小数",
        "dupont": (attr.get("dupont") or {}).get("contribution"),
        "operating_profit_bridge_yi": {
            k: (round(v / YI, 2) if isinstance(v, (int, float)) else v)
            for k, v in opb.items() if k != "note"
        },
        "cash_flow_bridge_items_yi": [
            {"item": it.get("item"),
             "amount_yi": round(it["amount"] / YI, 2) if isinstance(it.get("amount"), (int, float)) else None}
            for it in (cfb.get("items") or [])
        ],
        "cash_gap_yi": round(cfb["gap"] / YI, 2) if isinstance(cfb.get("gap"), (int, float)) else None,
    })

    # 6) 建议
    chain.append({
        "step": "建议",
        "item": "下一步动作",
        "actions": list(rule.get("suggestions", [])),
    })
    return chain


# --------------------------------------------------------------------------- #
# 行业剖面
# --------------------------------------------------------------------------- #
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "data", "industry_profiles")


def load_profile(industry: str | None, company_industry: str | None = None,
                 profile_dir: str | None = None) -> tuple[dict, str]:
    """按 --industry 显式指定 > 公司行业关键词自动匹配 > 默认剖面，返回 (profile, resolved_from)。"""
    pdir = os.path.abspath(profile_dir or PROFILE_DIR)
    index = json.load(open(os.path.join(pdir, "_index.json"), "r", encoding="utf-8"))
    entries = {p["profile_id"]: p for p in index.get("profiles", [])}

    if industry:
        ent = entries.get(industry)
        if not ent:
            raise SystemExit(f"[detect_risks] 未找到行业剖面 '{industry}'，"
                             f"可选：{', '.join(entries)}")
        prof = json.load(open(os.path.join(pdir, ent["file"]), "r", encoding="utf-8"))
        prof["_resolved_from"] = "--industry 显式指定"
        return prof, "explicit"

    text = str(company_industry or "")
    for p in index.get("profiles", []):
        if not p.get("keywords_any"):
            continue
        if any(kw and kw in text for kw in p.get("keywords_none", [])):
            continue
        if any(kw and kw in text for kw in p["keywords_any"]):
            prof = json.load(open(os.path.join(pdir, p["file"]), "r", encoding="utf-8"))
            prof["_resolved_from"] = f"按 company.industry='{text}' 关键词匹配"
            return prof, "auto"

    default = index.get("default_profile") or "manufacturing"
    ent = entries.get(default)
    prof = json.load(open(os.path.join(pdir, ent["file"]), "r", encoding="utf-8"))
    prof["_resolved_from"] = f"未匹配到行业，回落默认剖面 '{default}'"
    return prof, "default"


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="FinRadar / risk-radar 风险识别引擎")
    ap.add_argument("--ratios", required=True, help="financial-diagnosis 的 ratios 输出 JSON")
    ap.add_argument("--rules", required=True, help="risk_rules.json")
    ap.add_argument("--meta", default=None, help="可选的补充 meta JSON（如行业基准、审计意见）")
    ap.add_argument("--industry", default=None,
                    help="行业剖面 id（banking / manufacturing ...）。不给则按 company.industry 自动匹配")
    ap.add_argument("--profile-dir", default=None, help="行业剖面目录（默认 ../data/industry_profiles）")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    diag = json.load(open(args.ratios, "r", encoding="utf-8"))
    rules = json.load(open(args.rules, "r", encoding="utf-8"))
    meta_extra = json.load(open(args.meta, "r", encoding="utf-8")) if args.meta else None

    company_industry = ((diag.get("company") or {}).get("industry")
                        or (diag.get("meta") or {}).get("industry"))
    profile, _how = load_profile(args.industry, company_industry, args.profile_dir)

    result = detect(diag, rules, meta_extra, profile=profile)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False,
                  indent=2 if args.pretty else None,
                  separators=None if args.pretty else (",", ":"))
        f.write("\n")

    s = result["summary"]
    ip = result["industry_profile"]
    print(f"[OK] risks -> {args.output}")
    print(f"     行业剖面：{ip['profile_id']}（{ip['label']}）；{ip['resolved_from']}")
    print(f"     规则 {s['total_rules']} 条 | 适用 {s['in_scope_rules']} | 不适用 {s['not_applicable']} "
          f"| 触发 {s['triggered']} (重大 {s['by_severity']['high']} / 关注 {s['by_severity']['medium']} "
          f"/ 提示 {s['by_severity']['low']}) | 通过 {s['passed']} | 不可评估 {s['not_evaluable']}")
    print(f"     综合风险：{s['overall_risk_level']}（{s['overall_risk_score']}）  待核验 {len(result['review_queue'])} 项")
    for r in s["top_risks"]:
        print(f"       - [{r['severity_tag']}] {r['risk_id']} {r['risk_name']}")


if __name__ == "__main__":
    main()
