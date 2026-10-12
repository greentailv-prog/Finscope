#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
financial-diagnosis / compute_ratios.py
=======================================
B 模块第 1 段：财务指标计算引擎。

输入 : A 模块输出的 financial_data.json（统一接口里的 data.financials）
输出 : 统一接口里的 data.ratios（五类指标 + 归因 + 证据回链 + 待核验队列）

定位
----
- 纯函数式：同样的输入必然得到同样的输出，可复算、可回归测试。
- 不猜数：任何缺字段一律输出 null 并进 review_queue，绝不"用行业均值补"。
- 带出处：每个指标的输入项都能回溯到年报 source + page，供 E 前端与风险证据链使用。

用法
----
    python compute_ratios.py --input demo/input_financials.json --output demo/output_ratios.json
    python compute_ratios.py -i x.json -o y.json --pretty
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta

SCHEMA_VERSION = "finradar.diagnosis/1.0"

UNIT_FACTOR = {
    "元": 1.0, "CNY": 1.0, "人民币元": 1.0, "元(人民币)": 1.0,
    "千元": 1e3, "万元": 1e4, "百万元": 1e6, "百万": 1e6,
    "亿元": 1e8, "亿": 1e8,
    # 无量纲单位：不能被 default_unit 换算，否则比率会被金额单位放大
    "ratio": 1.0, "x": 1.0, "倍": 1.0, "days": 1.0, "天": 1.0,
    "%": 0.01, "percent": 0.01, "百分比": 0.01,
}

# 无量纲单位：这些字段在 evidence 里保留原始语义单位，不改写为「元」
DIMENSIONLESS_UNITS = {"ratio", "x", "倍", "days", "天", "%", "percent", "百分比"}

# 只用于展示的数值精度
PCT_KEYS_HINT = ("margin", "ratio", "growth", "roe", "roa", "roic", "turnover", "coverage")


def _load_field_labels() -> dict:
    """会计科目中文名映射表（data/field_labels.json）。

    取不到就返回空表——标签缺失只影响展示，绝不能让引擎跑不起来。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "field_labels.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("fields", {}) or {}
    except Exception:
        return {}


_FIELD_LABELS = _load_field_labels()


# --------------------------------------------------------------------------- #
# 数据访问层
# --------------------------------------------------------------------------- #
class Fin:
    """按 (metric, period) 取值，自动做单位归一 + 出处回链。"""

    def __init__(self, obj: dict):
        self.raw = obj or {}
        self.meta = self.raw.get("meta", {}) or {}
        self.fin = self.raw.get("financials", {}) or {}
        self.default_unit = self.meta.get("default_unit", "元")
        periods = self.meta.get("periods")
        if not periods:
            seen = set()
            for v in self.fin.values():
                if isinstance(v, dict):
                    for p in v.keys():
                        if isinstance(p, str) and p.isdigit():
                            seen.add(p)
            periods = sorted(seen)
        self.periods = [str(p) for p in periods]

    # ---- 取值 ----------------------------------------------------------- #
    def get(self, key: str, period: str):
        node = self.fin.get(key)
        if not isinstance(node, dict):
            return None
        cell = node.get(period)
        if cell is None:
            return None
        if isinstance(cell, dict):
            val = cell.get("value")
            unit = cell.get("unit")
        else:
            val, unit = cell, None
        if val is None:
            return None
        try:
            val = float(val)
        except (TypeError, ValueError):
            return None
        factor = self._factor(unit)
        return val * factor

    def _factor(self, unit):
        """单位换算系数。显式写了单位的按该单位换算；未写单位才回退 default_unit。
        显式写了但不在表里的（如 ratio / x / days），按无量纲处理为 1.0——
        绝不能套 default_unit，否则百分比会被金额单位放大一百万倍。"""
        if unit:
            f = UNIT_FACTOR.get(unit)
            return f if f is not None else 1.0
        return UNIT_FACTOR.get(self.default_unit, 1.0)

    def ref(self, key: str, period: str):
        """返回该 (metric, period) 的出处信息，供证据链使用。"""
        node = self.fin.get(key)
        if not isinstance(node, dict):
            return None
        cell = node.get(period)
        if not isinstance(cell, dict):
            cell = {"value": cell}
        raw_val = cell.get("value")
        unit = cell.get("unit") or self.default_unit
        factor = self._factor(unit)
        return {
            # value 为归一到「元」的口径，供下游计算与规则引用来使用
            "value": None if raw_val is None else raw_val * factor,
            # 无量纲字段（比率 / 倍数 / 天数）不做金额归一，unit 保持语义单位，
            # 否则下游无法判断"这是比率还是钱"，会漏生成 _pp（百分点）变量。
            "unit": unit if unit in DIMENSIONLESS_UNITS else "元",
            "unit_normalized": "元",
            # display_* 保留年报原文口径，供前端与证据链直接展示
            "display_value": raw_val,
            "display_unit": unit,
            "source": cell.get("source"),
            "page": cell.get("page"),
        }

    def has(self, key: str) -> bool:
        return isinstance(self.fin.get(key), dict)


def avg(a, b):
    if a is None or b is None:
        return None
    return (a + b) / 2.0


def div(a, b):
    """安全除法：分母缺失或为 0 时返回 None（不猜数、不静默吞错）。"""
    if a is None or b is None:
        return None
    if b == 0:
        return None
    try:
        return a / b
    except ZeroDivisionError:
        return None


# --------------------------------------------------------------------------- #
# 指标登记器
# --------------------------------------------------------------------------- #
class RatioBook:
    def __init__(self, fin: Fin, t: str, t1: str):
        self.fin = fin
        self.t = t          # 当期
        self.t1 = t1        # 上期
        self.r = {
            "growth": {}, "profitability": {}, "solvency": {},
            "efficiency": {}, "cashflow_quality": {}, "banking": {},
        }
        self.notes: list[dict] = []

    # 当期 / 上期 快捷取值
    def v(self, key, period=None):
        return self.fin.get(key, period or self.t)

    def p(self, key):
        return self.fin.get(key, self.t1)

    def put(self, cat, key, value, formula, inputs, prev=None, unit="ratio",
            higher_is_better=None, note=None):
        entry = {
            "value": value,
            "unit": unit,
            "formula": formula,
            "inputs": inputs,
            "prev": prev,
        }
        if value is not None and prev is not None:
            entry["delta"] = value - prev
        else:
            entry["delta"] = None
        if higher_is_better is not None:
            entry["higher_is_better"] = higher_is_better
        if value is None:
            entry["status"] = "not_meaningful"
            missing = [k for k, x in (inputs or {}).items() if x is None]
            self.notes.append({
                "metric": f"{cat}.{key}",
                "reason": "missing_or_invalid_input" if missing else "not_computable",
                "missing_inputs": missing,
                "note": note or "分母为 0 / 缺失输入，指标不可算，已置 null 并进入待核验队列",
            })
        else:
            entry["status"] = "ok"
        self.r[cat][key] = entry
        return entry


# 银行业不适用、需要在输出里显式标记而不是当成"算不出来"的通用指标。
# 与 risk-radar/data/industry_profiles/banking.json 的 metric_applicability 保持一致；
# 改任一侧都要同步另一侧（README 的"口径维护"一节有说明）。
BANKING_NA_METRICS = {
    "growth": ["cost_of_revenue_growth"],
    "profitability": ["gross_margin", "selling_expense_ratio", "admin_expense_ratio",
                      "rd_expense_ratio", "finance_expense_ratio", "period_expense_ratio",
                      "roic", "roic_minus_wacc", "ebit_margin"],
    "solvency": ["current_ratio", "quick_ratio", "cash_ratio", "interest_bearing_debt",
                 "interest_bearing_debt_ratio", "interest_bearing_debt_growth", "net_debt",
                 "cash_to_short_term_debt", "interest_coverage", "net_debt_to_ebitda",
                 "restricted_cash_ratio", "working_capital"],
    "efficiency": ["ar_turnover", "inventory_turnover", "ap_turnover", "dso", "dio", "dpo",
                   "cash_conversion_cycle", "total_asset_turnover", "fixed_asset_turnover",
                   "accounts_receivable_growth", "inventory_growth",
                   "ar_and_inventory_to_assets"],
    "cashflow_quality": ["ocf_to_net_income", "ocf_to_net_income_parent", "sales_cash_ratio",
                         "capex", "capex_to_ocf", "free_cash_flow", "fcf_to_revenue",
                         "ocf_to_interest_paid", "cf_financing_dependency"],
}

BANK_KEYWORDS = ("银行", "货币金融", "商业银行", "储蓄", "信用社")
BANK_EXCLUDE = ("银行IT", "金融信息服务", "金融设备")


def _infer_profile(meta: dict, obj: dict) -> str:
    """meta.industry_profile 显式指定优先；否则按行业关键词猜。猜不出用 general。"""
    text = " ".join([str(meta.get("industry") or ""),
                     str((obj.get("company") or {}).get("industry") or "")])
    if any(k in text for k in BANK_EXCLUDE):
        return "general"
    if any(k in text for k in BANK_KEYWORDS):
        return "banking"
    return "general"


def _banking_metrics(fin: Fin, bk: RatioBook, t: str, t1: str, periods: list):
    """银行业专项指标。银行没有应收/存货/毛利，通用指标里大半不适用，
    这里补上真正刻画银行的四组指标：息差与收入结构、资产质量、资本充足、资产负债匹配。
    披露值（NIM / 不良率 / 拨备覆盖率 / 资本充足率）一律直取年报披露口径，不做二次估算。"""
    def at(key, pd):
        return fin.get(key, pd)

    t2 = periods[-3] if len(periods) >= 3 else None
    rev = at("revenue", t)
    rev_p = at("revenue", t1)
    loans, loans_p = at("customer_loans_gross", t), at("customer_loans_gross", t1)
    deps, deps_p = at("customer_deposits", t), at("customer_deposits", t1)
    avg_loans = avg(loans, loans_p)

    def gc(key):
        return _growth(at(key, t), at(key, t1))

    def gp(key):
        return _growth(at(key, t1), at(key, t2)) if t2 else None

    def dt(key):
        """披露口径指标：本期值与上期值都直取年报。"""
        return V(key), P(key)

    V, P = bk.v, bk.p

    # ---- 息差与收入结构 ---- #
    nim, nim_p = dt("nim")
    bk.put("banking", "nim", nim,
           "净利息收益率 NIM（年报披露值）= 利息净收入 / 平均生息资产",
           {"nim_disclosed": nim}, nim_p, higher_is_better=True)
    spr, spr_p = dt("net_interest_spread")
    bk.put("banking", "net_interest_spread", spr,
           "净利息差（年报披露值）= 平均生息资产收益率 − 平均计息负债付息率",
           {"spread_disclosed": spr}, spr_p, higher_is_better=True)
    bk.put("banking", "net_interest_income_ratio",
           div(at("net_interest_income", t), rev),
           "利息净收入 / 营业收入",
           {"net_interest_income": at("net_interest_income", t), "revenue": rev},
           div(at("net_interest_income", t1), rev_p), higher_is_better=None)
    bk.put("banking", "fee_income_ratio",
           div(at("fee_income_net", t), rev),
           "手续费及佣金净收入 / 营业收入（中间业务收入占比）",
           {"fee_income_net": at("fee_income_net", t), "revenue": rev},
           div(at("fee_income_net", t1), rev_p), higher_is_better=True)
    bk.put("banking", "net_interest_income_growth", gc("net_interest_income"),
           "利息净收入同比增长率",
           {"cur": at("net_interest_income", t), "prev": at("net_interest_income", t1)},
           gp("net_interest_income"), higher_is_better=None)

    # ---- 成本 ---- #
    bk.put("banking", "cost_to_income",
           div(at("business_admin_expense", t), rev),
           "成本收入比 = 业务及管理费 / 营业收入",
           {"business_admin_expense": at("business_admin_expense", t), "revenue": rev},
           div(at("business_admin_expense", t1), rev_p), higher_is_better=False)
    bk.put("banking", "operating_expense_ratio",
           div(at("operating_expense", t), rev),
           "营业支出 / 营业收入（含信用减值损失）",
           {"operating_expense": at("operating_expense", t), "revenue": rev},
           div(at("operating_expense", t1), rev_p), higher_is_better=False)

    # ---- 资产质量 ---- #
    npl, npl_p = dt("npl_ratio")
    bk.put("banking", "npl_ratio", npl,
           "不良贷款率（年报披露值）= 不良贷款余额 / 客户贷款及垫款总额",
           {"npl_ratio_disclosed": npl}, npl_p, higher_is_better=False)
    pc, pc_p = dt("provision_coverage")
    bk.put("banking", "provision_coverage", pc,
           "拨备覆盖率（年报披露值）= 贷款减值准备 / 不良贷款余额",
           {"provision_coverage_disclosed": pc}, pc_p, higher_is_better=True)
    lpr, lpr_p = dt("loan_provision_ratio")
    bk.put("banking", "loan_provision_ratio", lpr,
           "贷款拨备率（年报披露值）= 贷款减值准备 / 客户贷款及垫款总额",
           {"loan_provision_ratio_disclosed": lpr}, lpr_p, higher_is_better=True)
    npl_bal = None if (loans is None or npl is None) else loans * npl
    npl_bal_p = None if (loans_p is None or npl_p is None) else loans_p * npl_p
    bk.put("banking", "npl_balance", npl_bal,
           "不良贷款余额（估算）= 客户贷款及垫款总额 × 不良贷款率",
           {"customer_loans_gross": loans, "npl_ratio": npl},
           npl_bal_p, unit="CNY", higher_is_better=False)
    credit_cost_p = (div(at("credit_impairment_loss", t1),
                         avg(at("customer_loans_gross", t1), at("customer_loans_gross", t2)))
                     if t2 else None)
    bk.put("banking", "credit_cost",
           div(at("credit_impairment_loss", t), avg_loans),
           "信用减值损失 / 平均客户贷款及垫款总额（口径偏宽：分子含全部金融资产的信用减值）",
           {"credit_impairment_loss": at("credit_impairment_loss", t),
            "avg_loans": avg_loans},
           credit_cost_p, higher_is_better=False)

    # ---- 资本充足 ---- #
    for key, label in (("cet1_ratio", "核心一级资本充足率"),
                       ("tier1_ratio", "一级资本充足率"),
                       ("capital_adequacy_ratio", "资本充足率")):
        v, vp = dt(key)
        bk.put("banking", key, v, f"{label}（年报披露值）",
               {f"{key}_disclosed": v}, vp, higher_is_better=True)
    bk.put("banking", "rwa_to_assets",
           div(at("rwa", t), at("total_assets", t)),
           "风险加权资产 / 总资产（RWA 密度）",
           {"rwa": at("rwa", t), "total_assets": at("total_assets", t)},
           div(at("rwa", t1), at("total_assets", t1)), higher_is_better=False)
    eq_total = at("total_equity", t)
    eq_total_p = at("total_equity", t1)
    bk.put("banking", "equity_to_assets",
           div(eq_total if eq_total is not None else at("equity_parent", t),
               at("total_assets", t)),
           "股东权益合计 / 总资产",
           {"total_equity": eq_total, "total_assets": at("total_assets", t)},
           div(eq_total_p if eq_total_p is not None else at("equity_parent", t1),
               at("total_assets", t1)), higher_is_better=True)

    # ---- 资产负债匹配 ---- #
    bk.put("banking", "loan_to_deposit", div(loans, deps),
           "存贷比 = 客户贷款及垫款总额 / 客户存款（2015 年起为监测指标，非监管指标）",
           {"customer_loans_gross": loans, "customer_deposits": deps},
           div(loans_p, deps_p), higher_is_better=False)
    bk.put("banking", "loan_growth", gc("customer_loans_gross"),
           "客户贷款及垫款总额同比增长率",
           {"cur": loans, "prev": loans_p}, gp("customer_loans_gross"),
           higher_is_better=None)
    bk.put("banking", "deposit_growth", gc("customer_deposits"),
           "客户存款同比增长率",
           {"cur": deps, "prev": deps_p}, gp("customer_deposits"),
           higher_is_better=None)

    # ---- 回报（银行口径） ---- #
    avg_ta = avg(at("total_assets", t), at("total_assets", t1))
    bk.put("banking", "roa_bank", div(at("net_income", t), avg_ta),
           "平均总资产回报率 = 净利润 / 平均总资产",
           {"net_income": at("net_income", t), "avg_total_assets": avg_ta},
           div(at("net_income", t1), avg(at("total_assets", t1), at("total_assets", t2)))
           if t2 else None, higher_is_better=True)
    avg_rwa = avg(at("rwa", t), at("rwa", t1))
    bk.put("banking", "rwa_return", div(at("net_income", t), avg_rwa),
           "风险加权资产收益率 = 净利润 / 平均风险加权资产（银行的'资本使用效率'口径）",
           {"net_income": at("net_income", t), "avg_rwa": avg_rwa},
           div(at("net_income", t1), avg(at("rwa", t1), at("rwa", t2)))
           if t2 else None, higher_is_better=True)

    # 普通股股东口径 ROE：银行归母权益里含优先股与永续债（其他权益工具），
    # 通用 ROE 把这些也算进分母，会系统性低估银行 ROE。
    # 年报披露的"加权平均净资产收益率"用的正是扣除其他权益工具后的口径。
    def _common_eq(pd):
        eq = at("equity_parent", pd)
        other = at("other_equity_instruments", pd)
        return None if eq is None else (eq - other if other is not None else None)

    def _common_np(pd):
        np_ = at("net_income_parent", pd)
        dist = at("other_equity_instrument_distribution", pd)
        return None if np_ is None else (np_ - dist if dist is not None else None)

    avg_ceq = avg(_common_eq(t), _common_eq(t1))
    bk.put("banking", "roe_common",
           div(_common_np(t), avg_ceq),
           "普通股股东口径 ROE =（归母净利润 − 其他权益工具持有者分配）/ 平均（归母权益 − 其他权益工具）；"
           "与年报'加权平均净资产收益率'口径一致（年报为加权时点，本处为期初期末平均，存在小幅差异）",
           {"net_income_parent_adj": _common_np(t), "avg_common_equity": avg_ceq},
           div(_common_np(t1), avg(_common_eq(t1), _common_eq(t2))) if t2 else None,
           higher_is_better=True)


# --------------------------------------------------------------------------- #
# 上期输入快照
# --------------------------------------------------------------------------- #
# 与期间无关的量：期间天数、外部假设（WACC 等），快照中原样保留
_PERIOD_FREE = ("days", "wacc")

_KEEP = object()  # 哨兵：表示直接使用 inputs 原值


def _prev_value(key: str, derived_all: dict, t1, t2, fin, periods):
    """把 inputs 里的变量名整体往前挪一个期间。

    revenue_t   （本期口径=2025）→ 上期快照取 2024
    revenue_t_1 （本期口径=2024）→ 上期快照取 2023
    avg_X       → 用原始字段算「上期与前前期」的平均余额
    X_disclosed → 去掉后缀后取上期披露值
    """
    if key in _PERIOD_FREE:
        return _KEEP

    base, target = key, t1
    if key.endswith("_t_1"):
        base, target = key[: -4], (t2 or t1)
    elif key.endswith("_t"):
        base, target = key[: -2], t1
    else:
        for suf in ("_prev", "_disclosed"):
            if base.endswith(suf) and len(base) > len(suf):
                base = base[: -len(suf)]
                break

    node = derived_all.get(target) or {}
    if base in node:
        return node[base]

    # avg_X 是计算期内的局部派生量，未进 derived_all，这里用原始字段自行还原。
    # 注意 periods 为升序（早→晚），因此「更早一期」的索引是 i-1。
    if base.startswith("avg_"):
        raw = base[4:]
        try:
            i = periods.index(target) if target in periods else -1
            v0 = fin.get(raw, target)
            vm1 = fin.get(raw, periods[i - 1]) if i > 0 else None
            return avg(v0, vm1)
        except Exception:
            return None

    try:
        return fin.get(base, target)
    except Exception:
        return None


def _attach_inputs_prev(bk, derived_all: dict, t1, t2, periods) -> None:
    """给每个指标补 inputs_prev：与 inputs 同键，值取上一期口径。"""
    if not t1:
        return
    for _cat, items in bk.r.items():
        for _key, entry in items.items():
            inputs = entry.get("inputs")
            if not isinstance(inputs, dict) or not inputs:
                continue
            snapshot = {}
            for vk, vv in inputs.items():
                pv = _prev_value(vk, derived_all, t1, t2, bk.fin, periods)
                snapshot[vk] = vv if pv is _KEEP else pv
            if snapshot:
                entry["inputs_prev"] = snapshot


# --------------------------------------------------------------------------- #
# 主计算
# --------------------------------------------------------------------------- #
def compute(obj: dict) -> dict:
    fin = Fin(obj)
    meta = fin.meta
    periods = fin.periods
    if len(periods) < 2:
        raise SystemExit("[compute_ratios] 至少需要两个期间才能计算增长率与周转率，请检查 meta.periods。")
    t, t1 = periods[-1], periods[-2]
    days = float(meta.get("days_in_year") or 365)
    wacc = meta.get("wacc")

    bk = RatioBook(fin, t, t1)
    V = bk.v
    P = bk.p

    # ===================== 派生量（derived） ===================== #
    derived_t, derived_p = {}, {}

    # 对所有期间都算一遍派生量，便于三年期样本计算"上期"口径的 ROA / ROIC / 周转率
    derived_all: dict[str, dict] = {pd: {} for pd in periods}

    def both(key, fn):
        for pd in periods:
            derived_all[pd][key] = fn(pd)
        derived_t[key] = fn(t)
        derived_p[key] = fn(t1)

    both("gross_profit", lambda pd: _sub(V("revenue", pd), V("cost_of_revenue", pd)))
    both("ebit", lambda pd: _add(V("operating_profit", pd), V("finance_expense", pd)))
    both("effective_tax_rate",
         lambda pd: div(V("income_tax_expense", pd), V("pretax_profit", pd)))
    both("ebitda", lambda pd: _add(
        _add(V("operating_profit", pd), V("finance_expense", pd)),
        V("depreciation_amortization", pd)))
    both("nopat", lambda pd: (lambda e, tr: None if (e is None or tr is None) else e * (1 - tr))(
        _add(V("operating_profit", pd), V("finance_expense", pd)),
        div(V("income_tax_expense", pd), V("pretax_profit", pd))))
    both("interest_bearing_debt", lambda pd: _sum(
        V("short_term_borrowings", pd), V("current_portion_lt_debt", pd),
        V("long_term_borrowings", pd), V("bonds_payable", pd)))
    both("short_term_interest_bearing_debt", lambda pd: _sum(
        V("short_term_borrowings", pd), V("current_portion_lt_debt", pd)))
    both("net_debt", lambda pd: _sub(
        _sum(V("short_term_borrowings", pd), V("current_portion_lt_debt", pd),
             V("long_term_borrowings", pd), V("bonds_payable", pd)),
        V("cash_and_equivalents", pd)))
    both("invested_capital", lambda pd: _add(
        _sum(V("short_term_borrowings", pd), V("current_portion_lt_debt", pd),
             V("long_term_borrowings", pd), V("bonds_payable", pd)),
        V("equity_parent", pd)))
    both("working_capital", lambda pd: _sub(
        V("total_current_assets", pd), V("total_current_liabilities", pd)))
    both("ar_total", lambda pd: _sum(
        V("accounts_receivable", pd), V("notes_receivable", pd), V("contract_assets", pd)))
    both("fcf", lambda pd: _sub(V("ocf", pd), V("capex", pd)))
    both("period_expense", lambda pd: _sum(
        V("selling_expense", pd), V("admin_expense", pd), V("rd_expense", pd),
        V("finance_expense", pd)))

    derived = derived_all

    def D(key, period=None):
        return derived[period or t].get(key)

    def DP(key):
        return derived[t1].get(key)

    # 三年期样本：计算"上期"口径的 ROA / ROIC（需要 t-2 的余额）
    t2 = periods[-3] if len(periods) >= 3 else None

    def D2(key):
        return derived_all[t2].get(key) if t2 else None

    # ===================== 1. 成长性 ===================== #
    def gr(key):
        return _growth(V(key), P(key))

    bk.put("growth", "revenue_growth", gr("revenue"),
           "营业收入（本期）/ 营业收入（上期）- 1",
           {"revenue_t": V("revenue"), "revenue_t_1": P("revenue")},
           higher_is_better=True)
    bk.put("growth", "net_income_growth", gr("net_income"),
           "净利润（本期）/ 净利润（上期）- 1",
           {"net_income_t": V("net_income"), "net_income_t_1": P("net_income")},
           higher_is_better=True)
    bk.put("growth", "net_income_parent_growth", gr("net_income_parent"),
           "归母净利润（本期）/ 归母净利润（上期）- 1",
           {"ni_parent_t": V("net_income_parent"), "ni_parent_t_1": P("net_income_parent")},
           higher_is_better=True)
    bk.put("growth", "net_income_deducted_growth", gr("net_income_deducted"),
           "扣非净利润（本期）/ 扣非净利润（上期）- 1",
           {"ni_ded_t": V("net_income_deducted"), "ni_ded_t_1": P("net_income_deducted")},
           higher_is_better=True)
    bk.put("growth", "cost_of_revenue_growth", gr("cost_of_revenue"),
           "营业成本（本期）/ 营业成本（上期）- 1",
           {"cogs_t": V("cost_of_revenue"), "cogs_t_1": P("cost_of_revenue")})
    bk.put("growth", "total_assets_growth", gr("total_assets"),
           "总资产（本期）/ 总资产（上期）- 1",
           {"ta_t": V("total_assets"), "ta_t_1": P("total_assets")})
    bk.put("growth", "equity_parent_growth", gr("equity_parent"),
           "归母净资产（本期）/ 归母净资产（上期）- 1",
           {"eq_t": V("equity_parent"), "eq_t_1": P("equity_parent")})
    bk.put("growth", "ocf_growth", gr("ocf"),
           "经营活动现金流量净额（本期）/ 经营活动现金流量净额（上期）- 1",
           {"ocf_t": V("ocf"), "ocf_t_1": P("ocf")}, higher_is_better=True)

    rg = bk.r["growth"]["revenue_growth"]["value"]
    npg = bk.r["growth"]["net_income_parent_growth"]["value"]
    bk.put("growth", "profit_revenue_scissors",
           None if (rg is None or npg is None) else rg - npg,
           "收入增速 - 归母净利润增速（>0 表示增收不增利）",
           {"revenue_growth": rg, "net_income_parent_growth": npg}, higher_is_better=False)

    # ===================== 2. 盈利能力 ===================== #
    rev, rev_p = V("revenue"), P("revenue")
    gm = div(D("gross_profit"), rev)
    gm_p = div(DP("gross_profit"), rev_p)
    bk.put("profitability", "gross_margin", gm,
           "(营业收入 - 营业成本) / 营业收入",
           {"revenue": rev, "cost_of_revenue": V("cost_of_revenue")}, gm_p,
           higher_is_better=True)
    bk.put("profitability", "net_margin", div(V("net_income"), rev),
           "净利润 / 营业收入", {"net_income": V("net_income"), "revenue": rev},
           div(P("net_income"), rev_p), higher_is_better=True)
    bk.put("profitability", "net_margin_parent", div(V("net_income_parent"), rev),
           "归母净利润 / 营业收入", {"net_income_parent": V("net_income_parent"), "revenue": rev},
           div(P("net_income_parent"), rev_p), higher_is_better=True)
    bk.put("profitability", "net_margin_deducted", div(V("net_income_deducted"), rev),
           "扣非净利润 / 营业收入", {"net_income_deducted": V("net_income_deducted"), "revenue": rev},
           div(P("net_income_deducted"), rev_p), higher_is_better=True)
    bk.put("profitability", "operating_margin", div(V("operating_profit"), rev),
           "营业利润 / 营业收入", {"operating_profit": V("operating_profit"), "revenue": rev},
           div(P("operating_profit"), rev_p), higher_is_better=True)
    bk.put("profitability", "ebit_margin", div(D("ebit"), rev),
           "EBIT / 营业收入，EBIT = 营业利润 + 财务费用",
           {"ebit": D("ebit"), "revenue": rev}, div(DP("ebit"), rev_p), higher_is_better=True)

    bk.put("profitability", "selling_expense_ratio", div(V("selling_expense"), rev),
           "销售费用 / 营业收入", {"selling_expense": V("selling_expense"), "revenue": rev},
           div(P("selling_expense"), rev_p), higher_is_better=False)
    bk.put("profitability", "admin_expense_ratio", div(V("admin_expense"), rev),
           "管理费用 / 营业收入", {"admin_expense": V("admin_expense"), "revenue": rev},
           div(P("admin_expense"), rev_p), higher_is_better=False)
    bk.put("profitability", "rd_expense_ratio", div(V("rd_expense"), rev),
           "研发费用 / 营业收入", {"rd_expense": V("rd_expense"), "revenue": rev},
           div(P("rd_expense"), rev_p), higher_is_better=None)
    bk.put("profitability", "finance_expense_ratio", div(V("finance_expense"), rev),
           "财务费用 / 营业收入", {"finance_expense": V("finance_expense"), "revenue": rev},
           div(P("finance_expense"), rev_p), higher_is_better=False)
    bk.put("profitability", "period_expense_ratio", div(D("period_expense"), rev),
           "(销售+管理+研发+财务费用) / 营业收入", {"period_expense": D("period_expense"), "revenue": rev},
           div(DP("period_expense"), rev_p), higher_is_better=False)

    # ROE / ROA / ROIC —— 一律用平均余额口径
    avg_eq = avg(V("equity_parent"), P("equity_parent"))
    avg_ta = avg(V("total_assets"), P("total_assets"))
    avg_ic = avg(D("invested_capital"), DP("invested_capital"))
    roe = div(V("net_income_parent"), avg_eq)
    roe_p = div(P("net_income_parent"), avg(P("equity_parent"), fin.get("equity_parent", periods[-3]) if len(periods) >= 3 else None))
    if roe_p is None:
        roe_p = None  # 上期 ROE 需要 t-2 净资产，缺则置空

    # 若提供了第三期，则补齐上期 ROE
    if len(periods) >= 3:
        t2 = periods[-3]
        roe_p = div(P("net_income_parent"), avg(P("equity_parent"), fin.get("equity_parent", t2)))

    bk.put("profitability", "roe", roe,
           "归母净利润 / ((期初归母净资产 + 期末归母净资产) / 2)",
           {"net_income_parent": V("net_income_parent"), "avg_equity_parent": avg_eq},
           roe_p, higher_is_better=True)
    roa_p = div(P("net_income"), avg(P("total_assets"), fin.get("total_assets", t2))) if t2 else None
    roic_p = div(DP("nopat"), avg(DP("invested_capital"), D2("invested_capital"))) if t2 else None
    bk.put("profitability", "roa", div(V("net_income"), avg_ta),
           "净利润 / 平均总资产（净利润含少数股东损益，与总资产口径匹配）",
           {"net_income": V("net_income"), "avg_total_assets": avg_ta}, roa_p, higher_is_better=True)
    bk.put("profitability", "roic", div(D("nopat"), avg_ic),
           "NOPAT / 平均投入资本；NOPAT = EBIT x (1 - 有效税率)；投入资本 = 有息负债 + 归母净资产",
           {"nopat": D("nopat"), "avg_invested_capital": avg_ic}, roic_p, higher_is_better=True)
    bk.put("profitability", "effective_tax_rate", D("effective_tax_rate"),
           "所得税费用 / 利润总额",
           {"income_tax_expense": V("income_tax_expense"), "pretax_profit": V("pretax_profit")},
           DP("effective_tax_rate"))
    bk.put("profitability", "deducted_to_parent", div(V("net_income_deducted"), V("net_income_parent")),
           "扣非净利润 / 归母净利润（衡量盈利含金量）",
           {"net_income_deducted": V("net_income_deducted"), "net_income_parent": V("net_income_parent")},
           div(P("net_income_deducted"), P("net_income_parent")), higher_is_better=True)
    bk.put("profitability", "roic_minus_wacc",
           None if (bk.r["profitability"]["roic"]["value"] is None or wacc is None)
           else bk.r["profitability"]["roic"]["value"] - float(wacc),
           "ROIC - WACC（<0 表示当期未创造经济价值）",
           {"roic": bk.r["profitability"]["roic"]["value"], "wacc": wacc},
           None if (roic_p is None or wacc is None) else roic_p - float(wacc),
           higher_is_better=True)

    # ===================== 3. 偿债能力 ===================== #
    bk.put("solvency", "current_ratio", div(V("total_current_assets"), V("total_current_liabilities")),
           "流动资产 / 流动负债",
           {"total_current_assets": V("total_current_assets"),
            "total_current_liabilities": V("total_current_liabilities")},
           div(P("total_current_assets"), P("total_current_liabilities")), higher_is_better=True)
    bk.put("solvency", "quick_ratio",
           div(_sub(V("total_current_assets"), V("inventory")), V("total_current_liabilities")),
           "(流动资产 - 存货) / 流动负债",
           {"total_current_assets": V("total_current_assets"), "inventory": V("inventory"),
            "total_current_liabilities": V("total_current_liabilities")},
           div(_sub(P("total_current_assets"), P("inventory")), P("total_current_liabilities")),
           higher_is_better=True)
    bk.put("solvency", "cash_ratio", div(V("cash_and_equivalents"), V("total_current_liabilities")),
           "货币资金 / 流动负债",
           {"cash_and_equivalents": V("cash_and_equivalents"),
            "total_current_liabilities": V("total_current_liabilities")},
           div(P("cash_and_equivalents"), P("total_current_liabilities")), higher_is_better=True)
    bk.put("solvency", "debt_to_assets", div(V("total_liabilities"), V("total_assets")),
           "总负债 / 总资产",
           {"total_liabilities": V("total_liabilities"), "total_assets": V("total_assets")},
           div(P("total_liabilities"), P("total_assets")), higher_is_better=False)
    bk.put("solvency", "equity_multiplier", div(V("total_assets"), V("equity_parent")),
           "总资产 / 归母净资产（期末口径，杜邦分解用平均口径）",
           {"total_assets": V("total_assets"), "equity_parent": V("equity_parent")},
           div(P("total_assets"), P("equity_parent")), higher_is_better=None)
    bk.put("solvency", "interest_bearing_debt", D("interest_bearing_debt"),
           "短期借款 + 一年内到期非流动负债 + 长期借款 + 应付债券",
           {"short_term_borrowings": V("short_term_borrowings"),
            "current_portion_lt_debt": V("current_portion_lt_debt"),
            "long_term_borrowings": V("long_term_borrowings"),
            "bonds_payable": V("bonds_payable")}, DP("interest_bearing_debt"), unit="CNY")
    bk.put("solvency", "interest_bearing_debt_ratio", div(D("interest_bearing_debt"), V("total_assets")),
           "有息负债 / 总资产",
           {"interest_bearing_debt": D("interest_bearing_debt"), "total_assets": V("total_assets")},
           div(DP("interest_bearing_debt"), P("total_assets")), higher_is_better=False)
    bk.put("solvency", "interest_bearing_debt_growth",
           _growth(D("interest_bearing_debt"), DP("interest_bearing_debt")),
           "有息负债（本期）/ 有息负债（上期）- 1",
           {"ibd_t": D("interest_bearing_debt"), "ibd_t_1": DP("interest_bearing_debt")},
           higher_is_better=False)
    bk.put("solvency", "net_debt", D("net_debt"),
           "有息负债 - 货币资金",
           {"interest_bearing_debt": D("interest_bearing_debt"),
            "cash_and_equivalents": V("cash_and_equivalents")}, DP("net_debt"), unit="CNY")
    bk.put("solvency", "cash_to_short_term_debt",
           div(V("cash_and_equivalents"), D("short_term_interest_bearing_debt")),
           "货币资金 / (短期借款 + 一年内到期非流动负债)",
           {"cash_and_equivalents": V("cash_and_equivalents"),
            "short_term_interest_bearing_debt": D("short_term_interest_bearing_debt")},
           div(P("cash_and_equivalents"), DP("short_term_interest_bearing_debt")),
           higher_is_better=True)
    bk.put("solvency", "interest_coverage", div(D("ebit"), V("interest_expense")),
           "EBIT / 利息费用",
           {"ebit": D("ebit"), "interest_expense": V("interest_expense")},
           div(DP("ebit"), P("interest_expense")), unit="x", higher_is_better=True)
    bk.put("solvency", "net_debt_to_ebitda", div(D("net_debt"), D("ebitda")),
           "净负债 / EBITDA",
           {"net_debt": D("net_debt"), "ebitda": D("ebitda")},
           div(DP("net_debt"), DP("ebitda")), unit="x", higher_is_better=False)
    bk.put("solvency", "restricted_cash_ratio", div(V("restricted_cash"), V("cash_and_equivalents")),
           "受限货币资金 / 货币资金",
           {"restricted_cash": V("restricted_cash"), "cash_and_equivalents": V("cash_and_equivalents")},
           div(P("restricted_cash"), P("cash_and_equivalents")), higher_is_better=False)
    bk.put("solvency", "working_capital", D("working_capital"),
           "流动资产 - 流动负债",
           {"total_current_assets": V("total_current_assets"),
            "total_current_liabilities": V("total_current_liabilities")},
           DP("working_capital"), unit="CNY")

    # ===================== 4. 营运能力 ===================== #
    avg_ar = avg(V("accounts_receivable"), P("accounts_receivable"))
    avg_inv = avg(V("inventory"), P("inventory"))
    avg_ap = avg(V("accounts_payable"), P("accounts_payable"))
    avg_fa = avg(V("fixed_assets"), P("fixed_assets"))

    ar_turn = div(rev, avg_ar)
    inv_turn = div(V("cost_of_revenue"), avg_inv)
    ap_turn = div(V("cost_of_revenue"), avg_ap)
    dso = div(days, ar_turn) if ar_turn else None
    dio = div(days, inv_turn) if inv_turn else None
    dpo = div(days, ap_turn) if ap_turn else None

    ar_turn_p = div(rev_p, avg(P("accounts_receivable"), fin.get("accounts_receivable", periods[-3]) if len(periods) >= 3 else None))
    if len(periods) >= 3:
        t2 = periods[-3]
        ar_turn_p = div(rev_p, avg(P("accounts_receivable"), fin.get("accounts_receivable", t2)))
        inv_turn_p = div(P("cost_of_revenue"), avg(P("inventory"), fin.get("inventory", t2)))
        ap_turn_p = div(P("cost_of_revenue"), avg(P("accounts_payable"), fin.get("accounts_payable", t2)))
    else:
        ar_turn_p = inv_turn_p = ap_turn_p = None
    dso_p = div(days, ar_turn_p) if ar_turn_p else None
    dio_p = div(days, inv_turn_p) if inv_turn_p else None
    dpo_p = div(days, ap_turn_p) if ap_turn_p else None

    bk.put("efficiency", "ar_turnover", ar_turn, "营业收入 / 平均应收账款",
           {"revenue": rev, "avg_accounts_receivable": avg_ar}, ar_turn_p, unit="x",
           higher_is_better=True)
    bk.put("efficiency", "inventory_turnover", inv_turn, "营业成本 / 平均存货",
           {"cost_of_revenue": V("cost_of_revenue"), "avg_inventory": avg_inv}, inv_turn_p,
           unit="x", higher_is_better=True)
    bk.put("efficiency", "ap_turnover", ap_turn, "营业成本 / 平均应付账款",
           {"cost_of_revenue": V("cost_of_revenue"), "avg_accounts_payable": avg_ap}, ap_turn_p,
           unit="x", higher_is_better=None)
    bk.put("efficiency", "dso", dso, "365 / 应收账款周转率（应收账款口径，不含票据与合同资产）",
           {"days": days, "ar_turnover": ar_turn}, dso_p, unit="days", higher_is_better=False)
    bk.put("efficiency", "dio", dio, "365 / 存货周转率",
           {"days": days, "inventory_turnover": inv_turn}, dio_p, unit="days", higher_is_better=False)
    bk.put("efficiency", "dpo", dpo, "365 / 应付账款周转率",
           {"days": days, "ap_turnover": ap_turn}, dpo_p, unit="days", higher_is_better=None)
    ccc = None if (dso is None or dio is None or dpo is None) else dso + dio - dpo
    ccc_p = None if (dso_p is None or dio_p is None or dpo_p is None) else dso_p + dio_p - dpo_p
    bk.put("efficiency", "cash_conversion_cycle", ccc, "DSO + DIO - DPO",
           {"dso": dso, "dio": dio, "dpo": dpo}, ccc_p, unit="days", higher_is_better=False)
    bk.put("efficiency", "total_asset_turnover", div(rev, avg_ta), "营业收入 / 平均总资产",
           {"revenue": rev, "avg_total_assets": avg_ta},
           div(rev_p, avg(P("total_assets"), fin.get("total_assets", periods[-3]) if len(periods) >= 3 else None)),
           unit="x", higher_is_better=True)
    bk.put("efficiency", "fixed_asset_turnover", div(rev, avg_fa), "营业收入 / 平均固定资产",
           {"revenue": rev, "avg_fixed_assets": avg_fa}, None, unit="x", higher_is_better=True)
    bk.put("efficiency", "accounts_receivable_growth",
           _growth(V("accounts_receivable"), P("accounts_receivable")),
           "应收账款（本期）/ 应收账款（上期）- 1",
           {"ar_t": V("accounts_receivable"), "ar_t_1": P("accounts_receivable")},
           higher_is_better=False)
    bk.put("efficiency", "inventory_growth", _growth(V("inventory"), P("inventory")),
           "存货（本期）/ 存货（上期）- 1",
           {"inv_t": V("inventory"), "inv_t_1": P("inventory")}, higher_is_better=False)
    bk.put("efficiency", "ar_and_inventory_to_assets",
           div(_add(D("ar_total"), V("inventory")), V("total_assets")),
           "(应收账款+应收票据+合同资产+存货) / 总资产",
           {"ar_total": D("ar_total"), "inventory": V("inventory"), "total_assets": V("total_assets")},
           div(_add(DP("ar_total"), P("inventory")), P("total_assets")), higher_is_better=False)

    # ===================== 5. 现金流质量 ===================== #
    bk.put("cashflow_quality", "ocf", V("ocf"), "经营活动产生的现金流量净额（原值）",
           {"ocf": V("ocf")}, P("ocf"), unit="CNY", higher_is_better=True)
    bk.put("cashflow_quality", "ocf_to_net_income", div(V("ocf"), V("net_income")),
           "经营活动现金流净额 / 净利润", {"ocf": V("ocf"), "net_income": V("net_income")},
           div(P("ocf"), P("net_income")), higher_is_better=True)
    bk.put("cashflow_quality", "ocf_to_net_income_parent", div(V("ocf"), V("net_income_parent")),
           "经营活动现金流净额 / 归母净利润（净现比）",
           {"ocf": V("ocf"), "net_income_parent": V("net_income_parent")},
           div(P("ocf"), P("net_income_parent")), higher_is_better=True)
    bk.put("cashflow_quality", "ocf_to_revenue", div(V("ocf"), rev),
           "经营活动现金流净额 / 营业收入", {"ocf": V("ocf"), "revenue": rev},
           div(P("ocf"), rev_p), higher_is_better=True)
    bk.put("cashflow_quality", "sales_cash_ratio", div(V("cash_received_from_sales"), rev),
           "销售商品、提供劳务收到的现金 / 营业收入（收现比）",
           {"cash_received_from_sales": V("cash_received_from_sales"), "revenue": rev},
           div(P("cash_received_from_sales"), rev_p), higher_is_better=True)
    bk.put("cashflow_quality", "capex", V("capex"), "购建固定资产、无形资产等支付的现金",
           {"capex": V("capex")}, P("capex"), unit="CNY")
    bk.put("cashflow_quality", "capex_to_ocf", div(V("capex"), V("ocf")),
           "资本开支 / 经营活动现金流净额（>1 表示投资靠外部融资输血）",
           {"capex": V("capex"), "ocf": V("ocf")}, div(P("capex"), P("ocf")),
           higher_is_better=False)
    bk.put("cashflow_quality", "free_cash_flow", D("fcf"),
           "经营活动现金流净额 - 资本开支",
           {"ocf": V("ocf"), "capex": V("capex")}, DP("fcf"), unit="CNY", higher_is_better=True)
    bk.put("cashflow_quality", "fcf_to_revenue", div(D("fcf"), rev),
           "自由现金流 / 营业收入", {"fcf": D("fcf"), "revenue": rev}, div(DP("fcf"), rev_p),
           higher_is_better=True)
    bk.put("cashflow_quality", "ocf_to_interest_paid", div(V("ocf"), V("interest_paid")),
           "经营活动现金流净额 / 已付利息",
           {"ocf": V("ocf"), "interest_paid": V("interest_paid")},
           div(P("ocf"), P("interest_paid")), unit="x", higher_is_better=True)
    bk.put("cashflow_quality", "payout_ratio", div(V("dividend_paid"), V("net_income_parent")),
           "已派发现金股利 / 归母净利润",
           {"dividend_paid": V("dividend_paid"), "net_income_parent": V("net_income_parent")},
           div(P("dividend_paid"), P("net_income_parent")), higher_is_better=None)
    bk.put("cashflow_quality", "cf_financing_dependency",
           None if V("ocf") in (None, 0) or V("cf_investing") is None
           else div(abs(V("cf_investing")) - V("ocf"), abs(V("cf_investing"))),
           "(投资现金流出 - 经营现金流) / 投资现金流出，>0 说明投资缺口需外部融资弥补",
           {"cf_investing": V("cf_investing"), "ocf": V("ocf")}, None, higher_is_better=False)
    bk.put("cashflow_quality", "goodwill_to_equity", div(V("goodwill"), V("equity_parent")),
           "商誉 / 归母净资产（商誉占归母净资产比，供风险诊断使用）",
           {"goodwill": V("goodwill"), "equity_parent": V("equity_parent")},
           div(P("goodwill"), P("equity_parent")), higher_is_better=False)

    # ===================== 银行业专项指标 ===================== #
    # 仅在行业剖面为 banking 时计算。银行的资产质量/资本/息差指标在制造业口径里不存在，
    # 单独成类，供 risk-radar 的 B01–B13 规则消费。
    industry_profile = meta.get("industry_profile") or _infer_profile(meta, obj)
    if industry_profile == "banking":
        _banking_metrics(fin, bk, t, t1, periods)

    # ===================== 上期输入快照 ===================== #
    # 为每个指标补一份 inputs_prev（与 inputs 同键、取上期口径的值），
    # 供看板 / 前端「点击指标 → 看公式与数据」时做本期 vs 上期对照。
    # 仅在 outputs 里新增可选字段，不改动既有结构，对下游向后兼容。
    _attach_inputs_prev(bk, derived_all, t1, t2, periods)

    # ===================== 归因 ===================== #
    attribution = _attribution(fin, bk, derived, t, t1, periods, days, wacc)

    # ===================== 证据回链 ===================== #
    evidence = {}
    for key in sorted(fin.fin.keys()):
        per_pd = {}
        for pd in periods:
            r = fin.ref(key, pd)
            if r and r.get("value") is not None:
                per_pd[pd] = r
        if per_pd:
            evidence[key] = per_pd

    # ===================== 待核验队列 ===================== #
    # 银行业：把不适用指标从"算不出来"改成"不适用"，不占待核验队列
    if industry_profile == "banking":
        na_set = {f"{cat}.{k}" for cat, keys in BANKING_NA_METRICS.items() for k in keys}
        bk.notes = [n for n in bk.notes if n["metric"] not in na_set]
        for cat, keys in BANKING_NA_METRICS.items():
            for k in keys:
                e = bk.r.get(cat, {}).get(k)
                if isinstance(e, dict):
                    e.update({"status": "not_applicable", "value": None, "prev": None,
                              "delta": None, "inputs": None,
                              "note": "银行业不适用该指标口径（无应收/存货/毛利/流动比率概念）"})

    review_queue = []
    for note in bk.notes:
        review_queue.append({
            "type": "uncomputable_ratio",
            "item": note["metric"],
            "reason": note["reason"],
            "missing_inputs": note["missing_inputs"],
            "suggested_action": "请回到 A 的抽取结果核对字段口径与页码，或由用户在对待核验队列确认后重算",
        })
    # 关键字段缺失检查（按行业剖面取不同的必需字段集）
    if industry_profile == "banking":
        required = ["revenue", "net_income_parent", "net_income", "total_assets",
                    "total_liabilities", "equity_parent", "customer_loans_gross",
                    "customer_deposits", "ocf", "npl_ratio", "provision_coverage",
                    "capital_adequacy_ratio", "cet1_ratio"]
    else:
        required = ["revenue", "cost_of_revenue", "net_income_parent", "total_assets",
                    "total_liabilities", "equity_parent", "accounts_receivable",
                    "inventory", "ocf"]
    for k in required:
        if not fin.has(k):
            review_queue.append({
                "type": "missing_required_field",
                "item": k,
                "reason": "A 未抽取到该字段，下游多项指标与风险规则不可算",
                "missing_inputs": [k],
                "suggested_action": "通知 A 补充抽取，或从年报合并报表附注人工补录",
            })

    # ============ 三表勾稽自检（不平项进待核验队列） ============ #
    checks = _articulation_checks(fin, periods)
    for it in checks["items"]:
        if it["status"] != "imbalanced":
            continue
        pct = it.get("diff_pct")
        review_queue.append({
            "type": "articulation_break",
            "item": f"{it['name']}（{it['period']}）",
            "reason": (f"三表勾稽不平：{it['formula']}；"
                       f"左 {it['left']:,.0f} 元 vs 右 {it['right']:,.0f} 元，"
                       f"差异 {it['diff']:,.0f} 元（占基准 {pct:.2%}，容差 1%）"
                       if pct is not None else
                       f"三表勾稽不平：{it['formula']}；左右两侧差异超容差"),
            "missing_inputs": [],
            "suggested_action": "B 不自动修正。请回到 A 的抽取结果核对相关科目的口径与页码，"
                               "确认是否串表、是否漏取附注拆分项，再重跑本引擎。",
        })

    # ===================== 出处汇总 ===================== #
    src = {}
    for key, per_pd in evidence.items():
        for pd, r in per_pd.items():
            if r.get("source"):
                src.setdefault(r["source"], set()).add(r.get("page"))
    sources = [{"source": s, "pages": sorted([p for p in pages if p is not None])}
               for s, pages in sorted(src.items())]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "generator": "financial-diagnosis/scripts/compute_ratios.py",
        "company": obj.get("company", {}),
        "period": {"current": t, "previous": t1, "all": periods},
        "meta": meta,
        "industry_profile": industry_profile,
        "assumptions": {
            "wacc": wacc,
            "days_in_year": days,
            "average_balance": "所有周转率 / 回报率类指标的分母一律使用 (期初 + 期末) / 2",
            "unit_normalized_to": "元",
        },
        "derived": {pd: {k: _r6(v) for k, v in derived_all[pd].items()} for pd in periods},
        "ratios": _round_ratios(bk.r),
        "checks": checks,
        "attribution": attribution,
        "evidence": evidence,
        "review_queue": review_queue,
        "sources": sources,
    }


# --------------------------------------------------------------------------- #
# 归因
# --------------------------------------------------------------------------- #
def _attribution(fin, bk, derived, t, t1, periods, days, wacc):
    R = bk.r

    # ---- 杜邦分解（平均口径，三项相乘严格闭合到 ROE） ---- #
    nm = R["profitability"]["net_margin_parent"]["value"]
    tat = R["efficiency"]["total_asset_turnover"]["value"]
    avg_eq = avg(fin.get("equity_parent", t), fin.get("equity_parent", t1))
    avg_ta = avg(fin.get("total_assets", t), fin.get("total_assets", t1))
    em = div(avg_ta, avg_eq)
    roe = R["profitability"]["roe"]["value"]

    nm_p = div(fin.get("net_income_parent", t1), fin.get("revenue", t1))
    tat_p = None
    em_p = None
    if len(periods) >= 3:
        t2 = periods[-3]
        rev_p = fin.get("revenue", t1)
        ta_p = fin.get("total_assets", t1)
        ta_p2 = fin.get("total_assets", t2)
        eq_p = fin.get("equity_parent", t1)
        eq_p2 = fin.get("equity_parent", t2)
        tat_p = div(rev_p, avg(ta_p, ta_p2))
        em_p = div(avg(ta_p, ta_p2), avg(eq_p, eq_p2))
    roe_p = R["profitability"]["roe"]["prev"]

    dupont = {"current": {}, "previous": {}, "contribution": {}}
    if None not in (nm, tat, em):
        dupont["current"] = {"net_margin": nm, "asset_turnover": tat,
                             "equity_multiplier": em, "roe": nm * tat * em}
    if None not in (nm_p, tat_p, em_p):
        dupont["previous"] = {"net_margin": nm_p, "asset_turnover": tat_p,
                              "equity_multiplier": em_p, "roe": nm_p * tat_p * em_p}
    if dupont["current"] and dupont["previous"]:
        c, p = dupont["current"], dupont["previous"]
        dupont["contribution"] = {
            "net_margin_effect": (c["net_margin"] - p["net_margin"]) * p["asset_turnover"] * p["equity_multiplier"],
            "asset_turnover_effect": c["net_margin"] * (c["asset_turnover"] - p["asset_turnover"]) * p["equity_multiplier"],
            "leverage_effect": c["net_margin"] * c["asset_turnover"] * (c["equity_multiplier"] - p["equity_multiplier"]),
            "roe_delta": c["roe"] - p["roe"],
        }

    # ---- 营业利润变动桥：规模 / 毛利率 / 费用率 / 其他 ---- #
    rev, rev_p = fin.get("revenue", t), fin.get("revenue", t1)
    op, op_p = fin.get("operating_profit", t), fin.get("operating_profit", t1)
    gm = R["profitability"]["gross_margin"]["value"]
    gm_p = R["profitability"]["gross_margin"]["prev"]
    er = R["profitability"]["period_expense_ratio"]["value"]
    er_p = R["profitability"]["period_expense_ratio"]["prev"]
    bridge = {}
    if None not in (rev, rev_p, op, op_p, gm, gm_p, er, er_p):
        opm_p = div(op_p, rev_p)
        scale = (rev - rev_p) * opm_p
        margin_eff = rev * (gm - gm_p)
        expense_eff = rev * (er_p - er)
        other = (op - op_p) - (scale + margin_eff + expense_eff)
        bridge = {
            "delta_operating_profit": op - op_p,
            "scale_effect": scale,
            "gross_margin_effect": margin_eff,
            "expense_ratio_effect": expense_eff,
            "other_effect": other,
            "note": "规模效应=Δ收入×基期营业利润率；毛利率效应=当期收入×Δ毛利率；费用率效应=当期收入×(基期费用率-当期费用率)；其他=残差（减值、其他收益、投资收益、营业外等）",
        }

    # ---- 净利润 → 经营现金流 调节桥 ---- #
    ni = fin.get("net_income", t)
    ocf = fin.get("ocf", t)
    da = fin.get("depreciation_amortization", t)
    imp = fin.get("impairment_loss", t)
    fe = fin.get("finance_expense", t)
    d_inv = _sub(fin.get("inventory", t), fin.get("inventory", t1))
    d_ar = _sub(_sum(fin.get("accounts_receivable", t), fin.get("notes_receivable", t),
                     fin.get("contract_assets", t)),
                _sum(fin.get("accounts_receivable", t1), fin.get("notes_receivable", t1),
                     fin.get("contract_assets", t1)))
    d_ap = _sub(fin.get("accounts_payable", t), fin.get("accounts_payable", t1))
    cash_bridge_items = []
    known = [("净利润", ni), ("折旧与摊销", da), ("资产减值损失", imp), ("财务费用（利息支出）", fe),
             ("存货的增加", -d_inv if d_inv is not None else None),
             ("经营性应收项目的增加", -d_ar if d_ar is not None else None),
             ("经营性应付项目的增加", d_ap)]
    running = 0.0
    for name, v in known:
        if v is None:
            cash_bridge_items.append({"item": name, "amount": None, "note": "A 未提供该字段"})
            continue
        cash_bridge_items.append({"item": name, "amount": v})
        running += v
    other_amt = None if (ni is None or ocf is None) else ocf - running
    cash_bridge_items.append({"item": "其他（递延税、其他经营性项目、汇兑等，倒轧）", "amount": other_amt})
    cash_bridge = {
        "net_income": ni, "ocf": ocf, "items": cash_bridge_items,
        "gap": None if (ni is None or ocf is None) else ocf - ni,
        "note": "用于定位'利润有现金没现金'：若缺口主要由应收/存货占用造成，属营运资金扩张；若由减值等倒轧项造成，需进一步核查",
    }

    return {
        "dupont": dupont,
        "operating_profit_bridge": bridge,
        "cash_flow_bridge": cash_bridge,
        "narrative_hint": "三段归因分别回答：ROE 变动由什么驱动（杜邦）、利润变动由什么驱动（毛利/费用/规模）、利润与现金的缺口从哪来（现金流桥）。Risk Radar 的证据链会直接引用这三段。",
    }


# --------------------------------------------------------------------------- #
# 三表勾稽自检（RULES.md 第 95–103 行承诺，v1.2 落地）
# --------------------------------------------------------------------------- #
# 铁律：B 只"查出"不平，绝不"修平"。任何不平都进 review_queue 交回 A 核对。
ARTICULATION_TOLERANCE = 0.01  # 差异超过对应科目绝对值的 1% 视为不平


def _ev_node(fin: Fin, key: str, period: str) -> dict:
    """取科目的证据节点（含出处、原文口径）。取不到返回 value=None。"""
    r = fin.ref(key, period)
    if not r:
        return {"value": None, "derived": False, "source": None, "page": None}
    r = dict(r)
    r["derived"] = False
    return r


def fin_label(key: str) -> str:
    """会计科目中文名。与 data/field_labels.json 保持一致（报表内名称为准）。"""
    return _FIELD_LABELS.get(key, key)


def _make_item(cid, name, statement, formula, symbolic, period, left, right,
               basis, inputs, note=None, status=None, derived_keys=()):
    """构造一条勾稽检查记录。差异 |left - right| 与容差 tol×basis 比较。"""
    tol_abs = ARTICULATION_TOLERANCE * basis if basis else None
    if status is None:
        if left is None or right is None or basis is None:
            status = "not_evaluable"
        else:
            diff = left - right
            status = "balanced" if abs(diff) <= tol_abs else "imbalanced"
    diff = None if (left is None or right is None) else left - right
    diff_pct = None if (diff is None or not basis) else diff / basis

    item = {
        "id": cid,
        "name": name,
        "statement": statement,
        "period": period,
        "formula": formula,
        "formula_symbolic": symbolic,
        "status": status,
        "left": left,
        "right": right,
        "diff": diff,
        "diff_pct": diff_pct,
        "tolerance_pct": ARTICULATION_TOLERANCE,
        "tolerance_abs": tol_abs,
        "tolerance_basis": basis,
        "inputs": inputs,
    }
    if note:
        item["note"] = note
    return item


def _minority_input(fin: Fin, period: str, te, ep) -> dict:
    """少数股东权益的证据节点：能直取就带出处，否则标注为倒轧值。

    倒轧值没有"年报原文口径"，这里按报表默认单位（meta.default_unit）折算
    display_value，避免同一张表里出现「百万元 / 亿元」混排。
    """
    if fin.has("minority_interest"):
        node = _ev_node(fin, "minority_interest", period)
        node["derived"] = False
        return node
    val = None if (te is None or ep is None) else te - ep
    return {
        "value": val,
        "derived": True,
        "derived_from": "所有者权益合计 − 归母股东权益",
        "display_value": None if val is None else val / UNIT_FACTOR.get(fin.default_unit, 1.0),
        "display_unit": fin.default_unit,
        "source": None, "page": None,
    }


def _missing_note(fin: Fin, keys: list, period: str):
    miss = [fin_label(k) for k in keys if fin.get(k, period) is None]
    return f"缺少科目：{'、'.join(miss)}，本项无法勾稽（不猜数、不跳过，进待核验队列）" if miss else None


def _articulation_checks(fin: Fin, periods: list, tol: float = ARTICULATION_TOLERANCE) -> dict:
    """三表勾稽自检。

    三条关系（RULES.md）：
      1. 资产负债表平衡：总资产 = 总负债 + 归母净资产 + 少数股东权益
      2. 现金净变动　　：期末现金 − 期初现金 = 经营 + 投资 + 筹资 + 汇率影响
      3. 利润表勾稽　　：利润总额 − 所得税费用 = 净利润 = 归母净利 + 少数股东损益
    其中第 3 条含两个恒等式，拆成两段分别出结果，便于定位断在哪一步。
    """
    items = []

    # ---------- 1) 资产负债表平衡（逐期） ---------- #
    for pd in periods:
        ta = fin.get("total_assets", pd)
        tl = fin.get("total_liabilities", pd)
        ep = fin.get("equity_parent", pd)
        te = fin.get("total_equity", pd)
        # 少数股东权益：A 抽到就直取，抽不到用「所有者权益合计 − 归母股东权益」倒轧
        mi = _resolve_val(fin, "minority_interest", pd, {}) if fin.has("minority_interest") \
            else (None if (te is None or ep is None) else te - ep)
        right = None if (tl is None or ep is None or mi is None) else tl + ep + mi
        inputs = {
            "总资产": _ev_node(fin, "total_assets", pd),
            "总负债": _ev_node(fin, "total_liabilities", pd),
            "归母股东权益": _ev_node(fin, "equity_parent", pd),
            "少数股东权益": _minority_input(fin, pd, te, ep),
        }
        note = _missing_note(fin, ["total_assets", "total_liabilities", "equity_parent"], pd)
        if note is None and te is None and not fin.has("minority_interest"):
            note = "缺少科目：所有者权益合计，且未抽取少数股东权益，无法倒轧"
        if note is None and right is None:
            note = "权益类科目缺失，无法倒轧少数股东权益"
        items.append(_make_item(
            "bs_balance", "资产负债表平衡", "资产负债表",
            "总资产 = 总负债 + 归母股东权益 + 少数股东权益",
            "total_assets - (total_liabilities + equity_parent + minority_interest)",
            pd, ta, right,
            abs(ta) if ta is not None else None, inputs, note,
        ))

    # ---------- 2) 利润表勾稽 · 第一段：利润总额 → 净利润 ---------- #
    for pd in periods:
        pbt = fin.get("pretax_profit", pd)
        tax = fin.get("income_tax_expense", pd)
        ni = fin.get("net_income", pd)
        right = None if (pbt is None or tax is None) else pbt - tax
        inputs = {
            "利润总额": _ev_node(fin, "pretax_profit", pd),
            "所得税费用": _ev_node(fin, "income_tax_expense", pd),
            "净利润": _ev_node(fin, "net_income", pd),
        }
        items.append(_make_item(
            "is_tax_bridge", "利润表勾稽·利润总额→净利润", "利润表",
            "利润总额 − 所得税费用 = 净利润",
            "pretax_profit - income_tax_expense - net_income",
            pd, right, ni,
            abs(pbt) if pbt is not None else None, inputs,
            _missing_note(fin, ["pretax_profit", "income_tax_expense", "net_income"], pd),
        ))

    # ---------- 3) 利润表勾稽 · 第二段：净利润 → 归母 + 少数股东 ---------- #
    # 注意：若少数股东损益是由「净利润 − 归母净利润」倒轧出来的，这条恒等式会
    # 退化成 A + (B − A) ≡ B，恒真、永远抓不到错，属于**伪勾稽**。
    # 因此只有在附注独立披露了该数（字段 minority_pnl）时才判 balanced /
    # imbalanced；否则一律 not_evaluable，并说明原因。宁可说"查不了"，
    # 也不能用一个恒真的式子冒充"查过了"。
    for pd in periods:
        ni = fin.get("net_income", pd)
        nip = fin.get("net_income_parent", pd)
        independent = fin.has("minority_pnl")
        # 左侧：由净利润与归母净利倒轧出的少数股东损益
        # 右侧：附注独立披露的少数股东损益
        # 两侧同源才是真勾稽；右侧缺失时本项无鉴别力，判无法勾稽。
        left = None if (ni is None or nip is None) else ni - nip
        right = fin.get("minority_pnl", pd) if independent else None
        inputs = {
            "净利润": _ev_node(fin, "net_income", pd),
            "归母净利润": _ev_node(fin, "net_income_parent", pd),
            "少数股东损益（独立披露）": _ev_node(fin, "minority_pnl", pd),
        }
        note = _missing_note(fin, ["net_income", "net_income_parent", "minority_pnl"], pd)
        items.append(_make_item(
            "is_minority_split", "利润表勾稽·净利润→归母+少数股东", "利润表",
            "净利润 − 归母净利润 = 少数股东损益（与附注独立披露值核对）",
            "(net_income - net_income_parent) - minority_pnl",
            pd, left, right,
            abs(ni) if ni is not None else None, inputs, note,
        ))

    # ---------- 4) 现金净变动勾稽（相邻两期之间） ---------- #
    for i in range(1, len(periods)):
        p0, p1 = periods[i - 1], periods[i]
        # 口径优先：现金流量表的「现金及现金等价物」(cf_cash_end) 才是与三项净额
        # 同源的口径；资产负债表的「货币资金 / 现金及存放中央银行款项」
        # (cash_and_equivalents) 含受限与准备金，直接拿来勾稽必然不平。
        cash_key = "cf_cash_end" if fin.has("cf_cash_end") else "cash_and_equivalents"
        cash_label = (fin_label("cf_cash_end") if cash_key == "cf_cash_end"
                      else fin_label("cash_and_equivalents"))
        c0 = fin.get(cash_key, p0)
        c1 = fin.get(cash_key, p1)
        ocf = fin.get("ocf", p1)
        icf = fin.get("cf_investing", p1)
        fcf = fin.get("cf_financing", p1)
        fx = fin.get("cf_fx_effect", p1) or fin.get("fx_effect", p1)  # 汇率影响，A 未必抽取
        left = None if (c1 is None or c0 is None) else c1 - c0
        parts = {"ocf": ocf, "cf_investing": icf, "cf_financing": fcf, "fx_effect": fx}
        miss = [fin_label(k) for k, v in parts.items() if v is None and k != "fx_effect"]
        if miss:
            right, note = None, f"缺少科目：{'、'.join(miss)}，本项无法勾稽"
        else:
            right = (ocf or 0) + (icf or 0) + (fcf or 0) + (fx or 0)
            note = None if fx is not None else \
                "未抽取'汇率变动对现金及现金等价物的影响'，该项按 0 参与勾稽；若差异超容差需人工核对"
        inputs = {
            f"期初{cash_label}": _ev_node(fin, cash_key, p0),
            f"期末{cash_label}": _ev_node(fin, cash_key, p1),
            "经营活动现金流净额": _ev_node(fin, "ocf", p1),
            "投资活动现金流净额": _ev_node(fin, "cf_investing", p1),
            "筹资活动现金流净额": _ev_node(fin, "cf_financing", p1),
        }
        if fx is not None:
            inputs["汇率变动对现金的影响"] = _ev_node(
                fin, "cf_fx_effect" if fin.has("cf_fx_effect") else "fx_effect", p1)
        # 容差基准取"现金净变动"与"三项净额合计"中较大者，避免净变动接近 0 时容差退化
        basis = max([abs(x) for x in (left, right) if x is not None] or [None])
        items.append(_make_item(
            "cf_reconcile", "现金净变动勾稽", "现金流量表",
            "期末现金 − 期初现金 = 经营活动 + 投资活动 + 筹资活动 + 汇率影响",
            "(cash_end - cash_begin) - (ocf + cf_investing + cf_financing + fx_effect)",
            f"{p0}→{p1}", left, right, basis, inputs, note,
        ))

    counts = {
        "total": len(items),
        "balanced": sum(1 for x in items if x["status"] == "balanced"),
        "imbalanced": sum(1 for x in items if x["status"] == "imbalanced"),
        "not_evaluable": sum(1 for x in items if x["status"] == "not_evaluable"),
    }
    # 顶层结论：只要有"不平"就是不平；全部无法勾稽则整段不可评估
    if counts["imbalanced"] > 0:
        overall = "imbalanced"
    elif counts["balanced"] > 0:
        overall = "balanced"
    else:
        overall = "not_evaluable"

    return {
        "schema": "三表勾稽自检",
        "tolerance_pct": tol,
        "tolerance_basis": "差异 |左 − 右| 超过对应科目绝对值的 1% 视为不平",
        "policy": "B 只查出不平，不自动修正；不平项写入 review_queue 交回 A 核对抽取结果",
        "overall": overall,
        "summary": counts,
        "items": items,
    }


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _add(a, b):
    return None if (a is None or b is None) else a + b


def _sub(a, b):
    return None if (a is None or b is None) else a - b


def _sum(*xs):
    if any(x is None for x in xs):
        return None
    return sum(xs)


def _growth(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b - 1.0


def _r6(v):
    return None if v is None else round(v, 6)


def _round_ratios(ratios: dict) -> dict:
    out = {}
    for cat, items in ratios.items():
        out[cat] = {}
        for k, e in items.items():
            ne = dict(e)
            if isinstance(ne.get("value"), float):
                ne["value"] = round(ne["value"], 6)
            if isinstance(ne.get("prev"), float):
                ne["prev"] = round(ne["prev"], 6)
            if isinstance(ne.get("delta"), float):
                ne["delta"] = round(ne["delta"], 6)
            if isinstance(ne.get("inputs"), dict):
                ne["inputs"] = {ik: (_r6(iv) if isinstance(iv, float) else iv)
                                for ik, iv in ne["inputs"].items()}
            out[cat][k] = ne
    return out


def _round_deep(o, nd=6):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, dict):
        return {k: _round_deep(v, nd) for k, v in o.items()}
    if isinstance(o, list):
        return [_round_deep(v, nd) for v in o]
    return o


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="FinRadar / financial-diagnosis 指标计算引擎")
    ap.add_argument("-i", "--input", required=True, help="A 模块输出的 financial_data.json")
    ap.add_argument("-o", "--output", required=True, help="输出的 ratios JSON")
    ap.add_argument("--pretty", action="store_true", help="缩进输出（默认紧凑）")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        obj = json.load(f)

    result = compute(obj)
    result = _round_deep(result)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        if args.pretty:
            json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    n = sum(len(v) for v in result["ratios"].values())
    bad = len(result["review_queue"])
    ck = result.get("checks", {}).get("summary", {})
    print(f"[OK] ratios -> {args.output}")
    print(f"     期间: {result['period']['current']} （对比期 {result['period']['previous']}）")
    print(f"     指标数: {n}   待核验: {bad}")
    print(f"     三表勾稽: {ck.get('balanced', 0)}/{ck.get('total', 0)} 平衡"
          f" | 不平 {ck.get('imbalanced', 0)} | 无法勾稽 {ck.get('not_evaluable', 0)}")
    for it in result.get("checks", {}).get("items", []):
        if it["status"] == "imbalanced":
            print(f"       [不平] {it['name']}（{it['period']}）差异 {it['diff']:,.0f} 元"
                  f"（{it['diff_pct']:.2%} > 1%）")


if __name__ == "__main__":
    main()
