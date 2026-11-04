#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_demo_inputs.py
=======================
生成多公司风险矩阵的演示输入：3 家制造业公司，全部是**合成数据**。

为什么要合成
------------
真实案例目前只有工商银行一家，无法构成同行业矩阵。
本脚本从 `financial-diagnosis/demo/input_financials.json` 派生 3 个不同风险画像，
仅用于验证矩阵引擎与前端呈现，**不得作为真实公司结论引用**。

合成后做一次口径修复，保证四类勾稽仍然成立：
    总资产 = 总负债 + 归母权益 + 少数股东权益
    利润总额 − 所得税 = 净利润
    净利润 − 归母净利润 = 少数股东损益
    期末现金 − 期初现金 = 经营 + 投资 + 筹资 + 汇率影响

用法
----
    python3 generate_demo_inputs.py            # 写入 inputs/
"""

from __future__ import annotations

import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BASE = os.path.join(ROOT, "financial-diagnosis", "demo", "input_financials.json")
OUT_DIR = os.path.join(HERE, "inputs")

SYNTH_NOTE = "演示样本（合成数据，非真实公司）"


# --------------------------------------------------------------------------- #
def scale(fin: dict, key: str, factor: float) -> None:
    if key not in fin:
        return
    for pd, cell in fin[key].items():
        if isinstance(cell, dict) and isinstance(cell.get("value"), (int, float)):
            cell["value"] = round(cell["value"] * factor, 6)
            cell["source"] = SYNTH_NOTE
            cell["page"] = None


def add(fin: dict, key: str, delta: float) -> None:
    if key not in fin:
        return
    for pd, cell in fin[key].items():
        if isinstance(cell, dict) and isinstance(cell.get("value"), (int, float)):
            cell["value"] = round(cell["value"] + delta, 6)


def value(fin: dict, key: str, pd: str, default=0.0) -> float:
    cell = (fin.get(key) or {}).get(pd)
    if isinstance(cell, dict) and isinstance(cell.get("value"), (int, float)):
        return float(cell["value"])
    return default


def put(fin: dict, key: str, pd: str, v: float) -> None:
    if key not in fin:
        return
    cell = fin[key].setdefault(pd, {})
    cell["value"] = round(v, 6)
    cell["source"] = SYNTH_NOTE
    cell["page"] = None


# --------------------------------------------------------------------------- #
def repair(doc: dict) -> None:
    """按四类勾稽关系重算派生科目，保证合成数据自身不矛盾。"""
    fin = doc["financials"]
    periods = doc["meta"]["periods"]

    # 权益结构：归母权益保持，少数股东权益沿用原差额
    minority = {}
    for pd in periods:
        minority[pd] = value(fin, "total_equity", pd) - value(fin, "equity_parent", pd)
        put(fin, "total_equity", pd, value(fin, "equity_parent", pd) + minority[pd])

    # 利润表：净利润与归母净利润按税、少数股东损益重算
    for pd in periods:
        ni = value(fin, "pretax_profit", pd) - value(fin, "income_tax_expense", pd)
        put(fin, "net_income", pd, ni)
        put(fin, "net_income_parent", pd, ni - value(fin, "minority_pnl", pd))

    # 资产负债表：总资产 = 负债 + 权益
    for pd in periods:
        put(fin, "total_assets", pd,
            value(fin, "total_liabilities", pd) + value(fin, "total_equity", pd))

    # 现金：按现金流量表勾稽倒推（期初沿用原值）
    for i, pd in enumerate(periods):
        if i == 0:
            continue
        prev = periods[i - 1]
        cash = (value(fin, "cash_and_equivalents", prev)
                + value(fin, "ocf", pd)
                + value(fin, "cf_investing", pd)
                + value(fin, "cf_financing", pd))
        put(fin, "cash_and_equivalents", pd, cash)

    # 流动项目：保持"其他流动资产/负债"的残差不变
    for pd in periods:
        orig_cur_a = value(fin, "total_current_assets", pd)
        comp_a = sum(value(fin, k, pd) for k in
                     ("cash_and_equivalents", "accounts_receivable",
                      "notes_receivable", "inventory"))
        residual_a = orig_cur_a - comp_a
        new_cur_a = comp_a + residual_a
        put(fin, "total_current_assets", pd, new_cur_a)

        comp_l = sum(value(fin, k, pd) for k in
                     ("accounts_payable", "short_term_borrowings", "current_portion_lt_debt"))
        residual_l = value(fin, "total_current_liabilities", pd) - comp_l
        put(fin, "total_current_liabilities", pd, comp_l + residual_l)


def make(base: dict, name: str, ticker: str, tweaks) -> dict:
    doc = copy.deepcopy(base)
    doc["company"]["name"] = name
    doc["company"]["ticker"] = ticker
    doc["company"]["report_source"] = SYNTH_NOTE
    doc["note"] = SYNTH_NOTE
    doc["meta"]["audit_opinion"] = "标准无保留意见"

    for key, factor in tweaks.get("scale", {}).items():
        scale(doc["financials"], key, factor)
    for key, delta in tweaks.get("add", {}).items():
        add(doc["financials"], key, delta)

    repair(doc)
    return doc


# --------------------------------------------------------------------------- #
def main() -> None:
    with open(BASE, encoding="utf-8") as f:
        base = json.load(f)

    companies = [
        ("company_a.json", "华衍智能装备股份有限公司", "DEMO-A.SH", {
            "scale": {
                "ocf": 2.20,
                "cf_investing": 0.60,
                "cf_financing": 0.40,
                "short_term_borrowings": 0.50,
                "long_term_borrowings": 0.50,
                "current_portion_lt_debt": 0.50,
                "accounts_receivable": 0.65,
                "inventory": 0.75,
                "revenue": 1.15,
                "cost_of_revenue": 1.05,
                "pretax_profit": 1.60,
                "income_tax_expense": 1.60,
                "goodwill": 0.70,
            },
        }),
        ("company_b.json", "瑞恒重工股份有限公司", "DEMO-B.SH", {
            "scale": {
                "accounts_receivable": 2.00,
                "notes_receivable": 1.50,
                "inventory": 1.30,
                "short_term_borrowings": 2.20,
                "long_term_borrowings": 1.80,
                "current_portion_lt_debt": 1.60,
                "ocf": 0.55,
                "cf_financing": 2.00,
            },
        }),
        ("company_c.json", "星海精密制造股份有限公司", "DEMO-C.SH", {
            "scale": {
                "revenue": 0.72,
                "cost_of_revenue": 0.80,
                "selling_expense": 0.85,
                "admin_expense": 0.85,
                "rd_expense": 0.85,
                "finance_expense": 1.20,
                "pretax_profit": 0.35,
                "income_tax_expense": 0.35,
                "ocf": -0.80,
                "accounts_receivable": 1.35,
                "inventory": 1.20,
                "cf_financing": 1.50,
            },
        }),
    ]

    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, name, ticker, tweaks in companies:
        doc = make(base, name, ticker, tweaks)
        path = os.path.join(OUT_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[OK] {path}")

    print("\n注意：以上均为合成数据，仅用于矩阵演示，不得作为真实公司结论。")


if __name__ == "__main__":
    main()
