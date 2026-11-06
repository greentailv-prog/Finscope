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
import re
import sys
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
# 动态阈值：只对规范 §6.3 点名的 5 条规则启用，其余一律 fixed。
# expr 用当期上下文求值；side=upper 表示高于阈值即危险，lower 表示低于阈值即危险。
# 规则与指标的对应关系写在这里，不散落到各条规则里，改口径只改这张表。
DYNAMIC_RULE_MAP = {
    "E01": {"expr": "accounts_receivable_growth - revenue_growth",
            "metric": "ar_growth_gap", "side": "upper"},
    "E04": {"expr": "inventory_growth - cost_of_revenue_growth",
            "metric": "inventory_growth_gap", "side": "upper"},
    "P06": {"expr": "gross_margin", "metric": "gross_margin", "side": "lower"},
    "E02": {"expr": "dso_delta", "metric": "dso_delta", "side": "upper"},
    "S01": {"expr": "debt_to_assets", "metric": "debt_to_assets", "side": "upper"},
}
PEER_MIN_SAMPLE = 3     # 同业少于 3 家回退固定阈值

# 行业剖面基准的最小样本量：与 calibrate.py 的分档一致（n>=15 calibrated，5<=n<15
# indicative），低于 5 视为 missing，不得用分位数判定。这里不 import calibrate.py
# （各脚本独立运行、零第三方依赖），常量保持同一含义。
BENCHMARK_MIN_SAMPLE = 5

# 银行专属规则（category=banking）在 D 的 CATEGORY_MAP 里没有对应项。
# 规范把 7 个类别冻结了，D 的映射表也不含 banking，若不改，D 会把 "banking"
# 原样透传成英文 slug 出现在报告里。这里按指标性质落到已有类别，只改交出去的
# category，规则文件本身保持 banking，行业适用性判断不受影响。
BANKING_RISK_CATEGORY = {
    "B01": "asset_quality",   # 不良贷款率抬升
    "B02": "asset_quality",   # 拨备覆盖率低于红线
    "B03": "asset_quality",   # 拨备覆盖率下降
    "B10": "asset_quality",   # 信用减值计提强度上升
    "B11": "asset_quality",   # 不良率降但拨备降
    "B04": "solvency",        # 资本充足率下滑
    "B05": "solvency",        # 核心一级逼近底线
    "B08": "solvency",        # 贷款增速快于存款
    "B09": "solvency",        # 存贷比抬升
    "B13": "solvency",        # 分红与资本同时承压
    "B06": "profitability",   # 净息差收窄
    "B07": "profitability",   # 成本收入比上升
    "B12": "profitability",   # RWA 收益率低于资本成本
}


def _out_category(rid: str, cat: str) -> str:
    """把内部 category 换成 D 的类别 slug。banking 逐条映射，其余原样。"""
    if cat != "banking":
        return cat
    return BANKING_RISK_CATEGORY.get(rid, "solvency")


def _peer_threshold_judge(rid: str, ctx: dict, comparison: dict | None):
    """有同业样本时，用同业分位替代固定阈值判定。

    返回 (fired, threshold_meta) 或 (None, None)。样本不足返回 None，交由固定阈值。
    """
    if not comparison or rid not in DYNAMIC_RULE_MAP:
        return None, None
    spec_cfg = DYNAMIC_RULE_MAP[rid]
    spec = ((comparison.get("thresholds") or {}).get(spec_cfg["metric"]) or {})
    n = int(spec.get("sample_n") or 0)
    thr = spec.get("value")
    if thr is None:
        # 阈值算不出来和「样本太少」是两回事，别用同一句话糊过去。
        if comparison.get("status") == "not_available":
            note = "本次未提供同业样本（status=not_available），用固定阈值"
        elif n == 0:
            note = ("同业阈值不可算：该指标在同业内均缺上期数据"
                    "（应收周转天数变动需三期应收），用固定阈值")
        else:
            note = "同业阈值缺数值（样本 %d 家），用固定阈值" % n
        return None, {"threshold_value": None, "threshold_source": "fixed",
                      "peer_sample_n": n, "peer_note": note}
    if n < PEER_MIN_SAMPLE:
        return None, {"threshold_value": thr, "threshold_source": "fixed",
                      "peer_sample_n": n,
                      "peer_note": "同业样本仅 %d 家（<%d），回退固定阈值" % (n, PEER_MIN_SAMPLE)}
    ok, val, _ = eval_expr(spec_cfg["expr"], ctx)
    if not ok or val is None:
        return None, {"threshold_value": thr, "threshold_source": "fixed",
                      "peer_sample_n": n, "peer_note": "本指标不可算，回退固定阈值"}
    fired = val > thr if spec_cfg["side"] == "upper" else val < thr
    return bool(fired), {
        "threshold_value": round(float(thr), 6),
        "threshold_source": spec.get("basis") or "peer_p75",
        "peer_sample_n": n,
        "threshold_metric_value": round(float(val), 6),
    }


def _benchmark_judge(rule: dict, ctx: dict, bmk_values: dict | None):
    """行业基准判定：规则声明 `benchmark_judge` 时，用离线校准的分位数重判。

    与 _peer_threshold_judge 的区别
    -------------------------------
    - 那边用 C 当次指定的同业样本（comparison.thresholds，n>=3）；
    - 这边用 B 的离线基准池：剖面 benchmarks（B 策展，如银行业的
      fetch_bank_samples 池）或 --benchmarks 传入的板块池
      （fetch_industry_samples 生成，覆盖任意东财行业板块），合并后 n>=5 才可用。
    两者不重叠时互不干扰；若同时命中，comparison 更具体，优先。

    规则文件里的声明形态（放在 rule 或 rule_overrides 的 modify 合并里均可）::

        "benchmark_judge": {
            "metric": "nim",                      # 基准池里的键
            "quantile": "median",                 # p10/p25/median/p75/p90
            "peer_expr": "nim < nim_industry_median",
            "note": "依据：……"
        }

    兜底原则：基准缺失、样本不足（n<5 或 status=missing）、或本指标当期不可算时，
    返回 (None, meta)，交回规则自身的 trigger 判定——绝不因校准数据缺失把本可
    判定的规则拖成 not_evaluable，也绝不静默当安全。回退原因写进 meta.peer_note。
    """
    cfg = rule.get("benchmark_judge")
    if not cfg:
        return None, None
    metric = cfg.get("metric") or ""
    quantile = cfg.get("quantile") or "median"

    def fallback(note: str):
        return None, {"threshold_value": rule.get("threshold"),
                      "threshold_source": "fixed_fallback",
                      "peer_sample_n": bmk.get("n") or 0, "peer_note": note}

    bmk = (bmk_values or {}).get(metric) or {}
    n = bmk.get("n") or 0
    status = bmk.get("status")
    qv = bmk.get(quantile)
    if status not in ("calibrated", "indicative") or n < BENCHMARK_MIN_SAMPLE:
        return fallback("行业基准样本不足（%s，n=%d），回退规则默认阈值" % (status or "未校准", n))
    if not isinstance(qv, (int, float)):
        return fallback("行业基准缺 %s 分位值，回退规则默认阈值" % quantile)
    ctx_var = "%s_industry_%s" % (metric, quantile)
    if ctx.get(ctx_var) is None:
        return fallback("行业基准未注入上下文，回退规则默认阈值")

    ok, fired, missing = eval_expr(cfg["peer_expr"], ctx)
    if not ok or fired is None:
        return fallback("同业阈值可判，但本指标当期不可算（缺 %s），回退规则默认阈值" % missing)

    meta = {"threshold_value": round(float(qv), 6),
            # 两条通道分开标注（与 D 对齐的口径）：
            #   本函数吃的是离线行业池（industry_profiles / peer_samples，年报季后刷新），
            #   不是当次请求的同业 —— 写 industry_*；
            #   _peer_threshold_judge 吃当次 --comparison 现场算的分位 —— 写 peer_*。
            # 混标会让人以为行业基准是这次请求算出来的，D 页面也要分开展示。
            "threshold_source": "industry_" + quantile,
            "peer_sample_n": int(n),
            "benchmark_status": status,
            "benchmark_pool": bmk.get("source")}
    # 本指标当期值：给证据链"计算"层用，写明判定时实际比较的两个数
    if isinstance(ctx.get(metric), (int, float)):
        meta["threshold_metric_value"] = round(float(ctx[metric]), 6)
    if cfg.get("note"):
        meta["peer_note"] = str(cfg["note"])
    return bool(fired), meta


def _wacc_judge(rule: dict, ctx: dict, wacc: dict | None):
    """WACC 敏感性判定：规则声明 `wacc_judge` 且 --wacc 传入 compute_wacc.py 产出时启用。

    规则文件里的声明形态::

        "wacc_judge": {
            "metric": "roe",             # 与资本成本比较的回报指标
            "side": "lt",                # lt: metric < 资本成本 → 触发
            "kind": "wacc",              # wacc（经典公式）/ equity_cost（银行 Ke）
            "transform": "raroc",        # 可选：metric_eff = rwa_return / capital_adequacy_ratio
                                         # （净利润/资本净额，与 Ke 同尺度可比）
            "peer_expr": "roe < wacc_point"   # 展示用表达式（wacc_* 已注入 ctx）
        }

    判定逻辑（敏感性三态，与项目「不猜数」原则对齐）：
    - metric 越过区间两端（对 low 与 high 同侧）→ triggered / passed，结论明确；
    - metric 落在假设区间内 → **结论随 WACC 假设翻转** → 返回 "sensitive"，
      主流程转 not_evaluable + review_queue 转人工——这本身是有信息量的结论
      （该公司的回报处在资本成本的合理争议区间），绝不取中值假装能判。

    无 --wacc 或本指标不可算时返回 (None, None)，规则维持原状态
    （P03/B12 因 trigger 引用 wacc 变量自然 not_evaluable，不伪装成安全）。
    """
    cfg = rule.get("wacc_judge")
    if not cfg or not isinstance(wacc, dict):
        return None, None
    metric = cfg.get("metric") or ""
    kind = cfg.get("kind") or "wacc"
    side = cfg.get("side") or "lt"
    # 规则声明的 kind 与文档键名对齐：equity_cost（银行 Ke）→ 文档 cost_of_equity
    band = wacc.get("cost_of_equity") if kind == "equity_cost" else wacc.get(kind)
    if not isinstance(band, dict):
        return None, None
    low, high, point = band.get("low"), band.get("high"), band.get("point")
    if not all(isinstance(x, (int, float)) for x in (low, high, point)):
        return None, None

    mv = ctx.get(metric)
    eff = mv
    if cfg.get("transform") == "raroc":
        car = ctx.get("capital_adequacy_ratio")
        if not isinstance(mv, (int, float)) or not isinstance(car, (int, float)) or car <= 0:
            return None, None
        eff = mv / car

    if not isinstance(eff, (int, float)):
        return None, None

    def fired_at(x):
        return eff < x if side == "lt" else eff > x

    f_lo, f_hi = fired_at(low), fired_at(high)
    # 折现率敏感性统一叫 wacc_sensitivity：银行用 Ke 替代 WACC，差异写在
    # threshold_note 里（口径说明属内容，不属枚举），不给 D 留两套取值。
    src = "wacc_sensitivity"
    beta_src = ((wacc.get("components") or {}).get("beta") or {}).get("source")

    def meta(extra_note=None):
        m = {"threshold_value": round(float(point), 6),
             "threshold_source": src,
             "wacc_low": low, "wacc_high": high, "wacc_point": point,
             "peer_note": extra_note}
        if isinstance(ctx.get(metric), (int, float)):
            m["threshold_metric_value"] = round(float(eff), 6)
        if beta_src:
            m["benchmark_status"] = "wacc_computed"
        return m

    cap_label = "股权成本 Ke（CAPM，银行不用经典 WACC）" if kind == "equity_cost" else "WACC"

    if f_lo and f_hi:
        note = "%s 敏感性判定：回报 %.2f%% 越过假设区间两端（%.2f%%–%.2f%%），结论明确" % (
            cap_label, eff * 100, low * 100, high * 100)
        if beta_src:
            note += "；β 来源：%s" % beta_src
        return bool(f_lo), meta(note)
    if not f_lo and not f_hi:
        note = "%s 敏感性判定：回报 %.2f%% 未触及假设区间两端（%.2f%%–%.2f%%），结论明确" % (
            cap_label, eff * 100, low * 100, high * 100)
        if beta_src:
            note += "；β 来源：%s" % beta_src
        return False, meta(note)
    # 区间内：结论随假设翻转
    return "sensitive", meta(
        "回报 %.2f%% 落在资本成本假设区间 %.2f%%–%.2f%% 内，结论随 WACC 假设翻转"
        "（低档 %.2f%% 判触发、高档 %.2f%% 判通过），转人工核验" % (
            eff * 100, low * 100, high * 100, low * 100, high * 100))


_THRESHOLD_BASIS_LABELS = {
    # 当次同业分位：--comparison 由 D 传的 peer_financials 现场算出
    "peer_p25": "同业 P25", "peer_p75": "同业 P75", "peer_median": "同业中位数",
    # 离线行业基准：年报季后刷新的样本池，与当次请求无关
    "industry_p10": "行业基准 P10", "industry_p25": "行业基准 P25",
    "industry_median": "行业基准中位数", "industry_p75": "行业基准 P75",
    "industry_p90": "行业基准 P90",
    "wacc_sensitivity": "折现率敏感性中值",
}


def _peer_display(disp, rid: str, thr_meta: dict | None):
    """把生效阈值写进触发说明，避免页面上还显示写死的 60%。

    规范 §6.3：阈值变了，trigger 文字要同步显示实际阈值。
    """
    src = (thr_meta or {}).get("threshold_source")
    if not thr_meta or src in ("fixed", "fixed_fallback") or not disp:
        return disp
    v = thr_meta.get("threshold_value")
    if v is None:
        return disp
    if rid == "E02":
        shown = "%.1f 天" % v
    else:
        shown = "%.2f%%" % (v * 100)
    basis = _THRESHOLD_BASIS_LABELS.get(src) or src
    if src == "wacc_sensitivity":
        # 折现率类：展示整个假设区间——单看中值会误以为是精确数
        lo = thr_meta.get("wacc_low")
        hi = thr_meta.get("wacc_high")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            return "本期阈值 = %s %s（假设区间 %.2f%%–%.2f%%）；规则原表述：%s" % (
                basis, shown, lo * 100, hi * 100, disp)
        return "本期阈值 = %s %s；规则原表述：%s" % (basis, shown, disp)
    sample = thr_meta.get("peer_sample_n") or 0
    # 实际阈值放前面：否则页面上会先看到写死的"5pp"，再看到 8.28%，读者不知道哪个生效。
    if src.startswith("industry_"):
        # 离线池的样本是年报季后刷新的历史样本，不是本次请求的同业，措辞要分开，
        # 否则读者会以为是这次现场算出来的分位
        return "本期阈值 = %s %s（离线样本 %d 家）；原表述：%s" % (basis, shown, sample, disp)
    return "本期阈值 = %s %s（样本 %d 家）；原表述：%s" % (basis, shown, sample, disp)


def detect(diag: dict, rules_doc: dict, meta_extra: dict | None = None,
           profile: dict | None = None, comparison: dict | None = None,
           benchmarks_doc: dict | None = None, wacc: dict | None = None) -> dict:
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

    # ---- 行业基准：剖面基准（B 策展）+ 板块池（--benchmarks 传入，任意行业）合并 ----
    # 板块池更细（东财细分行业），同一指标两者都有时板块池优先；
    # n<5 或 missing 的板块池指标不参与合并，保持剖面原值（兜底原则）。
    prof_bmk = ((profile.get("benchmarks") or {}).get("values") or {})
    eff_bmk = {k: dict(v) for k, v in prof_bmk.items() if isinstance(v, dict)}
    bmk_origin = {k: "profile" for k in eff_bmk}
    board_meta = None
    if benchmarks_doc:
        board_meta = {"board_code": benchmarks_doc.get("board_code"),
                      "board_name": benchmarks_doc.get("board_name"),
                      "as_of": benchmarks_doc.get("as_of")}
        for m, spec in (benchmarks_doc.get("metrics") or {}).items():
            if not isinstance(spec, dict):
                continue
            if (spec.get("status") in ("calibrated", "indicative")
                    and (spec.get("n") or 0) >= BENCHMARK_MIN_SAMPLE):
                eff_bmk[m] = dict(spec)
                bmk_origin[m] = "board:" + str(board_meta["board_name"] or board_meta["board_code"])

    # ---- 行业剖面：把基准分位数注入 ctx，供规则与模板使用 ---- #
    for name, spec in eff_bmk.items():
        if not isinstance(spec, dict):
            continue
        for q in ("p10", "p25", "median", "p75", "p90"):
            v = spec.get(q)
            if isinstance(v, (int, float)):
                ctx[f"{name}_industry_{q}"] = float(v)
                ctx[f"{name}_industry_{q}_pp"] = float(v) * 100

    # ---- WACC 敏感性区间注入 ctx（compute_wacc.py 产出，--wacc 传入）----
    # 注入 wacc_low/wacc_point/wacc_high 与 cost_of_equity_* 供规则表达式与
    # 证据链引用；判定本身走 _wacc_judge 的两端敏感性，不用中值硬判。
    for kind in ("wacc", "cost_of_equity"):
        band = (wacc or {}).get(kind)
        if not isinstance(band, dict):
            continue
        for k in ("low", "point", "high"):
            v = band.get(k)
            if isinstance(v, (int, float)):
                ctx[f"{kind}_{k}"] = float(v)
                ctx[f"{kind}_{k}_pp"] = float(v) * 100

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
                "category": _out_category(rid, cat),
                "category_internal": cat if cat == "banking" else None,
                "category_label": categories.get(cat),
                "status": "not_applicable",
                "severity": None,
                "severity_tag": None,
                "score": None,
                "trigger": rule.get("trigger"),
                "trigger_display": rule.get("trigger_display"),
                "threshold": rule.get("threshold"),
                "threshold_value": (rule.get("threshold")
                                    if isinstance(rule.get("threshold"), (int, float)) else None),
                "threshold_source": "fixed",
                "threshold_basis": rule.get("threshold_basis"),
                "peer_sample_n": 0,
                "evidence_required": rule.get("evidence_required", []),
                "confidence": rule.get("confidence"),
                "explanation": f"本行业（{profile.get('label', '未识别')}）不适用：{na_reason}",
                "evidence_chain": [],
                "trigger_values": {},
            })
            continue

        ok, fired, missing = eval_expr(rule["trigger"], ctx)
        active_rule = rule

        # 阈值来源：默认固定阈值。
        # ① 规范 §6.3 点名的 5 条规则在同业样本 ≥3 家时改用同业分位重判（C 当次指定的可比组）；
        # ② 规则声明 benchmark_judge 且行业基准已校准（n≥5）时改用行业分位重判（B 自建样本池）。
        # comparison 的可比组更具体，两者同时命中时 ① 优先，② 只兜 ① 没覆盖的规则。
        peer_fired, thr_meta = _peer_threshold_judge(rid, ctx, comparison)
        if peer_fired is None:
            bench_fired, bench_meta = _benchmark_judge(rule, ctx, eff_bmk)
            # 回退（bench_fired=None）也要把 fallback meta 写上卡：
            # threshold_source=fixed_fallback + 回退原因，读者才知道为什么没用同业阈值。
            if bench_meta is not None:
                thr_meta = bench_meta
            if bench_fired is not None:
                peer_fired = bench_fired
                cfg = rule.get("benchmark_judge") or {}
                if cfg.get("peer_expr"):
                    # trigger_values 与证据链要反映实际参与判定的表达式，
                    # 否则卡上写的是 delta 阈值、实际比较的却是行业分位。
                    # trigger_display 同步换成 _peer_display 处理后的生效阈值文案。
                    active_rule = dict(rule, trigger=cfg["peer_expr"],
                                       trigger_display=_peer_display(
                                           rule.get("trigger_display"), rid, thr_meta))
        if peer_fired is None:
            # ③ 规则声明 wacc_judge 且 --wacc 传入时用敏感性区间重判。
            #    区间内结论翻转 → "sensitive" → not_evaluable + review_queue 转人工。
            w_fired, w_meta = _wacc_judge(rule, ctx, wacc)
            if w_meta is not None:
                thr_meta = w_meta
            if w_fired == "sensitive":
                ok, fired, missing = False, None, ["WACC 敏感性区间内结论翻转，转人工核验"]
            elif w_fired is not None:
                peer_fired = w_fired
                cfg = rule.get("wacc_judge") or {}
                if cfg.get("peer_expr"):
                    active_rule = dict(rule, trigger=cfg["peer_expr"],
                                       trigger_display=_peer_display(
                                           rule.get("trigger_display"), rid, thr_meta))
        if peer_fired is not None:
            ok, fired, missing = True, peer_fired, []

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

        # threshold_value 只放数值。P06 这类规则的 threshold 在规则文件里写的是
        # 变量名（"industry_gross_margin_benchmark"），原样抄进数值字段会让
        # 页面把变量名当阈值显示，所以非数值一律置 null，表达式原文留在 trigger 里。
        _tv = (thr_meta or {}).get("threshold_value", rule.get("threshold"))
        if not isinstance(_tv, (int, float)):
            _tv = None
        item = {
            "risk_id": rid,
            "risk_name": rule.get("risk_name"),
            "risk_name_en": rule.get("risk_name_en"),
            "category": _out_category(rid, cat),
            "category_internal": cat if cat == "banking" else None,
            "category_label": categories.get(cat),
            "status": status,
            "severity": severity,
            "severity_tag": (severity_scale.get(severity) or {}).get("tag") if severity else None,
            "score": score,
            "trigger": active_rule.get("trigger"),
            "trigger_display": _peer_display(rule.get("trigger_display"), rid, thr_meta),
            "threshold": rule.get("threshold"),
            "threshold_value": _tv,
            "threshold_source": (thr_meta or {}).get("threshold_source", "fixed"),
            "peer_sample_n": (thr_meta or {}).get("peer_sample_n", 0),
            # threshold_basis 是规则默认阈值的性质（regulatory / self_delta / convention /
            # peer_percentile），由规则文件声明；threshold_source 是本次判定实际用的来源。
            # 一个静态、一个动态，不要混。
            "threshold_basis": rule.get("threshold_basis"),
            "threshold_note": (thr_meta or {}).get("peer_note"),
            "benchmark_status": (thr_meta or {}).get("benchmark_status"),
            "benchmark_pool": (thr_meta or {}).get("benchmark_pool"),
            "evidence_required": rule.get("evidence_required", []),
            "confidence": rule.get("confidence"),
        }

        if status == "triggered":
            item["explanation"] = _render(rule.get("explanation_template", ""), ctx)
            item["suggestions"] = list(rule.get("suggestions", []))
            item["evidence_chain"] = _evidence_chain(active_rule, ctx, diag, cur, prev)
            item["trigger_values"] = {
                v: ctx.get(v) for v in vars_in(active_rule["trigger"]) if v in ctx
            }
        elif status == "passed":
            item["explanation"] = "规则已执行，条件不成立，本项无异常。"
            item["evidence_chain"] = []
            item["trigger_values"] = {
                v: ctx.get(v) for v in vars_in(active_rule["trigger"]) if v in ctx
            }
        else:
            miss_txt = ("、".join(str(m) for m in missing)
                        if isinstance(missing, list) else str(missing))
            if miss_txt.startswith("WACC 敏感性"):
                # 敏感性翻转：不是缺数据，是结论不唯一——两种结果都写清楚
                item["explanation"] = ("结论不唯一：" + miss_txt + "。"
                                       "已转人工核验，不做单点假设。")
            else:
                item["explanation"] = (
                    f"无法判定：表达式引用的变量缺失（{miss_txt}），已转人工核验，"
                    "不做'无风险'假设。"
            )
            item["evidence_chain"] = []
            wj = rule.get("wacc_judge") or {}
            item["trigger_values"] = {}
            if thr_meta and (thr_meta.get("wacc_low") is not None):
                if isinstance(ctx.get(wj.get("metric") or ""), (int, float)):
                    item["trigger_values"][wj["metric"]] = ctx[wj["metric"]]
                item["trigger_values"]["wacc_low"] = thr_meta["wacc_low"]
                item["trigger_values"]["wacc_high"] = thr_meta["wacc_high"]
            review_queue.append({
                "type": "risk_not_evaluable",
                "item": f"{rid} {rule.get('risk_name')}",
                "reason": miss_txt,
                "missing_inputs": [miss_txt] if missing else [],
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
            # 全有全无的布尔看不出进度：把已校准指标与覆盖度一并透出（诚实标注）
            "benchmarks_coverage": (profile.get("benchmarks") or {}).get("coverage"),
            "benchmarks_calibrated_metrics": (profile.get("benchmarks") or {}).get("calibrated_metrics") or [],
            # --benchmarks 板块池信息与逐指标来源（profile=剖面策展 / board:XX=板块池）
            "benchmarks_board": board_meta,
            "benchmarks_origin": bmk_origin,
            # WACC 敏感性区间摘要（compute_wacc.py 产出）：给 D 显示"阈值怎么来的"。
            # 无 --wacc 时为 null——P03/B12 维持 not_evaluable，诚实缺数。
            "wacc": ({"company": (wacc or {}).get("company"),
                      "wacc_band": (wacc or {}).get("wacc"),
                      "cost_of_equity_band": (wacc or {}).get("cost_of_equity"),
                      "beta_source": ((wacc or {}).get("components") or {}).get("beta", {}).get("source"),
                      "risk_free_rate": ((wacc or {}).get("components") or {}).get("risk_free_rate")}
                     if wacc else None),
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
        # 规范 §6.1：risks 只放触发的卡，其余进 rules_evaluated。
        # 但 D 的 from_b.py 是按 status 从 risks 里分流的，直接改结构会把它打断，
        # 所以 risks 保留全量（向后兼容），另给两个规范字段。D 后续可切到这两个字段。
        "risks_triggered": [r for r in risks if r["status"] == "triggered"],
        "rules_evaluated": [r for r in risks if r["status"] != "triggered"],
        "comparison_status": (comparison or {}).get("status") if comparison else None,
        "review_queue": review_queue,
    }


# --------------------------------------------------------------------------- #
# 证据链 / 模板渲染
# --------------------------------------------------------------------------- #
def _render(tpl: str, ctx: dict) -> str:
    """渲染说明模板。

    整串 format 会在第一个缺失变量处抛错，导致**本来能填的变量也留成占位符**
    （例如「财务费用率由 {finance_expense_ratio_prev:.2%} 升至 12.3%」）。
    所以失败后退化为逐个替换：能填的填，确实缺的写「—」。
    """
    if not tpl:
        return ""
    try:
        return tpl.format(**ctx)
    except (KeyError, IndexError, ValueError, TypeError):
        pass

    def rep(m):
        name, spec = m.group(1), m.group(2) or ""
        v = ctx.get(name)
        if v is None:
            return "—"
        try:
            return format(v, spec[1:] if spec.startswith(":") else "")
        except (ValueError, TypeError):
            return str(v)

    return re.sub(r"\{([A-Za-z_]\w*)(:[^}]*)?\}", rep, tpl)


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
# 板块池自动解析（--benchmarks auto）
# --------------------------------------------------------------------------- #
BOARDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "data", "peer_samples", "boards")
BOARD_CACHE = os.path.join(BOARDS_DIR, "_company_board.json")


def resolve_board_pool(diag: dict, ensure: bool = False) -> tuple[dict | None, str]:
    """按 ratios 里的公司代码自动解析所属板块并读取本地板块池。

    与行业剖面的三级解析对齐：工作台输入公司代码/名称后无需手动指路，
    引擎自己找到板块池。遵循「离线校准，在线只读本地」原则：
    - 解析板块码最多几次轻量行情请求（结果缓存到 _company_board.json，
      第二次起零网络）；同业分位数**只从本地池文件读**。
    - 本地无池时不抓同业数据，除非显式给 --ensure-pool（一次性建池，
      之后仍走本地缓存）；否则在说明文字里给出建池命令，判定照常回退。
    返回 (池文档 | None, 说明文字)。
    """
    comp = diag.get("company") or {}
    code = str(comp.get("ticker_code") or comp.get("ticker") or "")
    if not re.fullmatch(r"\d{6}", code):
        return None, "无有效 6 位公司代码（%s），跳过板块池" % (code or "空")

    os.makedirs(BOARDS_DIR, exist_ok=True)
    cache = {}
    if os.path.exists(BOARD_CACHE):
        try:
            cache = json.load(open(BOARD_CACHE, "r", encoding="utf-8"))
        except Exception:
            cache = {}

    bk, bname = cache.get(code) or (None, None)
    if not bk:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import fetch_industry_samples as fis
            bk, bname = fis.resolve_board(None, code)
            cache[code] = {"bk": bk, "name": bname}
            with open(BOARD_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)
                f.write("\n")
        except Exception as e:
            return None, "板块解析失败（%s），跳过板块池" % e

    pool_path = os.path.join(BOARDS_DIR, "%s.json" % bk)
    if os.path.exists(pool_path):
        try:
            doc = json.load(open(pool_path, "r", encoding="utf-8"))
            return doc, "板块池 %s %s（本地缓存）" % (bk, bname or "")
        except Exception as e:
            return None, "板块池 %s 读取失败（%s）" % (bk, e)

    if ensure:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            fis_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "fetch_industry_samples.py")
            import subprocess
            subprocess.run([sys.executable, fis_path, "--code", code, "--write"],
                           check=True, capture_output=True, text=True, timeout=300)
            doc = json.load(open(pool_path, "r", encoding="utf-8"))
            return doc, "板块池 %s %s（--ensure-pool 现场新建）" % (bk, bname or "")
        except Exception as e:
            return None, "板块池 %s 现场建池失败（%s），回退固定阈值" % (bk, e)

    return None, ("板块池 %s %s 尚未建立，相关规则回退固定阈值。"
                  "建池：python3 fetch_industry_samples.py --code %s --write"
                  % (bk, bname or "", code))


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="FinRadar / risk-radar 风险识别引擎")
    ap.add_argument("--ratios", required=True, help="financial-diagnosis 的 ratios 输出 JSON")
    ap.add_argument("--rules", required=True, help="risk_rules.json")
    ap.add_argument("--meta", default=None, help="可选的补充 meta JSON（如行业基准、审计意见）")
    ap.add_argument("--industry", default=None,
                    help="行业剖面 id（banking / manufacturing ...）。不给则按 company.industry 自动匹配")
    ap.add_argument("--profile-dir", default=None, help="行业剖面目录（默认 ../data/industry_profiles）")
    ap.add_argument("--comparison", default=None,
                    help="同业对比 JSON（build_comparison.py 产出）。给了就对 5 条规则启用同业分位阈值")
    ap.add_argument("--benchmarks", default=None,
                    help="板块级同业基准池（fetch_industry_samples.py 产出）。传 'auto' 则按公司代码"
                         "自动解析所属板块并读取本地池（无池不建，提示建池命令）；也可传池文件路径。"
                         "任意行业可用：声明了 benchmark_judge 的规则改用板块分位数判定，缺失则回退固定阈值")
    ap.add_argument("--ensure-pool", action="store_true",
                    help="配合 --benchmarks auto：本地无池时现场建池（一次性，之后仍走本地缓存）")
    ap.add_argument("--wacc", default=None,
                    help="WACC 敏感性区间（compute_wacc.py 产出）。声明了 wacc_judge 的规则"
                         "（P03/B12）改用区间两端重判，区间内结论翻转则转人工；不给则维持 not_evaluable")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    diag = json.load(open(args.ratios, "r", encoding="utf-8"))
    rules = json.load(open(args.rules, "r", encoding="utf-8"))
    meta_extra = json.load(open(args.meta, "r", encoding="utf-8")) if args.meta else None
    comparison = json.load(open(args.comparison, "r", encoding="utf-8")) if args.comparison else None
    wacc_doc = json.load(open(args.wacc, "r", encoding="utf-8")) if args.wacc else None

    company_industry = ((diag.get("company") or {}).get("industry")
                        or (diag.get("meta") or {}).get("industry"))
    profile, _how = load_profile(args.industry, company_industry, args.profile_dir)

    pool_note = None
    if args.benchmarks == "auto":
        benchmarks_doc, pool_note = resolve_board_pool(diag, ensure=args.ensure_pool)
    else:
        benchmarks_doc = json.load(open(args.benchmarks, "r", encoding="utf-8")) if args.benchmarks else None

    result = detect(diag, rules, meta_extra, profile=profile, comparison=comparison,
                    benchmarks_doc=benchmarks_doc, wacc=wacc_doc)

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
    if pool_note:
        print(f"     板块池：{pool_note}")
    print(f"     规则 {s['total_rules']} 条 | 适用 {s['in_scope_rules']} | 不适用 {s['not_applicable']} "
          f"| 触发 {s['triggered']} (重大 {s['by_severity']['high']} / 关注 {s['by_severity']['medium']} "
          f"/ 提示 {s['by_severity']['low']}) | 通过 {s['passed']} | 不可评估 {s['not_evaluable']}")
    print(f"     综合风险：{s['overall_risk_level']}（{s['overall_risk_score']}）  待核验 {len(result['review_queue'])} 项")
    for r in s["top_risks"]:
        print(f"       - [{r['severity_tag']}] {r['risk_id']} {r['risk_name']}")


if __name__ == "__main__":
    main()
