#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts_test_checks.py
======================
三表勾稽自检的回归测试。

为什么要单独写这个测试
----------------------
一个只会输出"全部平衡"的检查器，和根本没有检查器，在界面上看起来一模一样。
所以必须证明它 **抓得到** 失衡 —— 用「注入已知错误 → 断言被抓出」的方式，
把检查器本身也纳入可回归验证的范围，而不是靠"跑一遍没报错"就宣称可用。

覆盖的用例
----------
  T1 平衡样本：三表应全部判 balanced
  T2 注入资产负债表失平：总负债虚增 → bs_balance 判 imbalanced，其余不受影响
  T3 注入利润表失平：归母净利虚增 → is_minority_split 判 imbalanced
  T4 注入现金流失平：筹资净额虚增 → cf_reconcile 判 imbalanced
  T5 缺失科目 → 对应项判 not_evaluable（不猜数、不默认通过）
  T6 容差边界：差异恰为 1% 判 balanced，略超 1% 判 imbalanced
  T7 不平项必须进 review_queue，且带 suggested_action

用法
----
    python3 scripts_test_checks.py            # 跑全部用例
    python3 scripts_test_checks.py -v         # 显示每条检查明细
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "financial-diagnosis", "scripts"))
import compute_ratios as CR  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
DEMO_INPUT = os.path.join(ROOT, "financial-diagnosis", "demo", "input_financials.json")

PASS, FAIL = [], []


def _load():
    with open(DEMO_INPUT, "r", encoding="utf-8") as f:
        return json.load(f)


def _checks(obj):
    return CR.compute(obj)["checks"]


def _status_of(checks, cid, period=None):
    out = [it["status"] for it in checks["items"]
           if it["id"] == cid and (period is None or it["period"] == period)]
    return out


def expect(cond, msg):
    if cond:
        PASS.append(msg)
    else:
        FAIL.append(msg)
    print(("  [PASS] " if cond else "  [FAIL] ") + msg)
    return cond


# --------------------------------------------------------------------------- #
def t1_balanced():
    print("\n[T1] 平衡样本应全部判 balanced")
    ck = _checks(_load())
    expect(ck["overall"] == "balanced", f"overall = balanced（实际 {ck['overall']}）")
    expect(ck["summary"]["imbalanced"] == 0,
           f"不平项 = 0（实际 {ck['summary']['imbalanced']}）")
    expect(ck["summary"]["not_evaluable"] == 0,
           f"无法勾稽项 = 0（实际 {ck['summary']['not_evaluable']}）")
    expect(ck["summary"]["total"] == 11,
           f"检查项总数 = 11（3期×2项 + 2段现金流；实际 {ck['summary']['total']}）")


def t2_bs_break():
    print("\n[T2] 注入资产负债表失平（总负债虚增 30%）")
    obj = _load()
    for pd in ("2023", "2024", "2025"):
        obj["financials"]["total_liabilities"][pd]["value"] *= 1.3
    ck = _checks(obj)
    expect(_status_of(ck, "bs_balance") == ["imbalanced"] * 3,
           f"bs_balance 三期全部 imbalanced（实际 {_status_of(ck,'bs_balance')}）")
    expect(set(_status_of(ck, "is_tax_bridge")) == {"balanced"},
           "is_tax_bridge 不受影响，仍为 balanced")
    expect(ck["overall"] == "imbalanced", "overall = imbalanced")


def t3_is_break():
    print("\n[T3] 注入利润表失平（归母净利虚增 20%）")
    obj = _load()
    for pd in ("2023", "2024", "2025"):
        obj["financials"]["net_income_parent"][pd]["value"] *= 1.2
    ck = _checks(obj)
    expect(_status_of(ck, "is_minority_split") == ["imbalanced"] * 3,
           f"is_minority_split 三期全部 imbalanced（实际 {_status_of(ck,'is_minority_split')}）")
    expect(set(_status_of(ck, "is_tax_bridge")) == {"balanced"},
           "is_tax_bridge 仍为 balanced（断在第二段，定位准确）")


def t4_cf_break():
    print("\n[T4] 注入现金流失平（筹资净额虚增 50 亿）")
    obj = _load()
    u = CR.UNIT_FACTOR[obj["financials"]["cf_financing"]["2025"]["unit"]]
    obj["financials"]["cf_financing"]["2025"]["value"] += 5e9 / u
    ck = _checks(obj)
    st = _status_of(ck, "cf_reconcile")
    expect(st == ["balanced", "imbalanced"],
           f"仅 2024→2025 段 imbalanced，2023→2024 不受影响（实际 {st}）")


def t5_missing():
    print("\n[T5] 缺失科目应判 not_evaluable（不猜数、不默认通过）")
    obj = _load()
    obj["financials"].pop("cf_investing", None)
    ck = _checks(obj)
    expect(_status_of(ck, "cf_reconcile") == ["not_evaluable"] * 2,
           f"cf_reconcile 两段均 not_evaluable（实际 {_status_of(ck,'cf_reconcile')}）")
    it = [x for x in ck["items"] if x["id"] == "cf_reconcile"][0]
    expect("缺少科目" in (it.get("note") or ""), "note 中明确列出缺失科目名")


def t6_tolerance():
    print("\n[T6] 容差边界：1% 判平衡，略超 1% 判不平")
    base = _load()
    # 容差基准是「总资产」，而被扰动的是「总负债」，两者量级不同：
    # 总资产 218.4 亿、总负债 135.2 亿，故负债需虚增约 1.62% 才逼近总资产 1% 的容差。
    def probe(ratio):
        obj = copy.deepcopy(base)
        obj["financials"]["total_liabilities"]["2025"]["value"] *= (1.0 + ratio)
        return [x for x in _checks(obj)["items"]
                if x["id"] == "bs_balance" and x["period"] == "2025"][0]

    a = probe(0.0100)   # 约 0.62% 总资产 → 容差内
    b = probe(0.0250)   # 约 1.55% 总资产 → 超容差
    print(f"       [容差内] 负债+1.00%%，差异占总资产 {a['diff_pct']:.3%} -> {a['status']}")
    print(f"       [超容差] 负债+2.50%%，差异占总资产 {b['diff_pct']:.3%} -> {b['status']}")
    expect(a["status"] == "balanced", "容差内判 balanced")
    expect(b["status"] == "imbalanced", "超容差判 imbalanced")
    expect(abs(a["diff_pct"]) < 0.01 <= abs(b["diff_pct"]), "差异占比跨越 1% 阈值")
    expect(abs(a["diff"]) <= a["tolerance_abs"] < abs(b["diff"]),
           " |差异| 与容差绝对值的关系符合预期")


def t7_review_queue():
    print("\n[T7] 不平项必须进 review_queue 且给出处置建议")
    obj = _load()
    obj["financials"]["total_liabilities"]["2025"]["value"] *= 1.2
    res = CR.compute(obj)
    brk = [q for q in res["review_queue"] if q["type"] == "articulation_break"]
    expect(len(brk) == 1, f"恰好 1 条 articulation_break（实际 {len(brk)}）")
    if brk:
        expect(bool(brk[0].get("suggested_action")), "带 suggested_action")
        expect("不自动修正" in brk[0]["suggested_action"],
               "suggested_action 明确写'不自动修正'（B 的边界）")


TESTS = [t1_balanced, t2_bs_break, t3_is_break, t4_cf_break,
         t5_missing, t6_tolerance, t7_review_queue]


def main():
    ap = argparse.ArgumentParser(description="三表勾稽自检回归测试")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印检查明细")
    args = ap.parse_args()

    print("=" * 62)
    print(" 三表勾稽自检 · 回归测试")
    print("=" * 62)

    if args.verbose:
        ck = _checks(_load())
        print("\n--- 基准样本检查明细 ---")
        for it in ck["items"]:
            print(f"  {it['status']:14s} {it['name']:30s} {it['period']:10s} "
                  f"diff={it['diff']}")
        print(f"  summary = {json.dumps(ck['summary'], ensure_ascii=False)}")

    for t in TESTS:
        t()

    print("\n" + "=" * 62)
    print(f" 结果：通过 {len(PASS)} | 失败 {len(FAIL)}")
    if FAIL:
        print("\n 失败用例：")
        for m in FAIL:
            print(f"   - {m}")
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
