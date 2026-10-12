#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
覆盖度自检 —— 回答一个高频问题：「为什么有些指标没算出来？」

对 financial-diagnosis 的输出做体检，把「未算出」拆成三类原因，
并给出可执行的补齐建议。三者语义完全不同，绝不能混为一谈：

  not_applicable  行业口径不成立 → 正确行为，不是缺陷，无需补数据
  not_evaluable   输入缺失或分母为 0 → 需要补数据，否则指标永远算不出来
  ok              正常算出

用法:
  python3 scripts_check_coverage.py financial-diagnosis/demo/output_ratios.json
  python3 scripts_check_coverage.py cases/icbc-601398/output_ratios.json -v
  python3 scripts_check_coverage.py --all          # 检查全部输出
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

CAT_LABEL = {
    "growth": "成长性",
    "profitability": "盈利能力",
    "solvency": "偿债能力",
    "efficiency": "营运能力",
    "cashflow_quality": "现金流质量",
    "banking": "银行业专属",
    "insurance": "保险业专属",
    "brokerage": "券商业专属",
    "real_estate": "地产业专属",
}

# 常见缺失字段 → 补齐建议
FIELD_ADVICE = {
    "wacc": "由 C 的估值模块提供资本成本，回填 meta.wacc",
    "industry_gross_margin_benchmark": "由 C 从可比公司池算行业中位数，回填 meta.industry_gross_margin_benchmark",
    "accounts_receivable": "从年报「应收账款」附注抽取期末原值",
    "inventory": "从年报「存货」附注抽取期末原值",
    "accounts_payable": "从年报「应付账款」附注抽取期末原值",
    "capex": "从现金流量表「购建固定资产、无形资产和其他长期资产支付的现金」抽取",
    "interest_paid": "从现金流量表「分配股利、利润或偿付利息支付的现金」附注拆分",
    "interest_expense": "从利润表「财务费用」附注拆分",
    "rd_expense": "从利润表「研发费用」抽取，无则填 0 并标注",
    "rd_capitalized": "从「开发支出」附注的本年资本化金额抽取",
    "restricted_cash": "从「货币资金」附注的受限部分抽取",
    "goodwill": "从资产负债表「商誉」抽取，无则填 0",
    "dividend_paid": "从现金流量表「分配股利、利润或偿付利息支付的现金」拆分",
}


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.2f}%"


def _fmt(v, unit):
    if v is None:
        return "—"
    if unit == "ratio":
        return f"{v * 100:.2f}%"
    if unit == "days":
        return f"{v:.1f} 天"
    if unit == "x":
        return f"{v:.2f} 倍"
    if unit == "CNY":
        return f"{v / 1e8:,.2f} 亿"
    return str(v)


def check(path: str, verbose: bool = False) -> dict:
    d = json.load(io.open(path, encoding="utf-8"))
    R = d.get("ratios") or {}
    # 指标输出里 industry_profile 是字符串 id，风险输出里是详细字典，两种都兼容
    raw_prof = d.get("industry_profile")
    if isinstance(raw_prof, dict):
        prof = raw_prof
    else:
        prof = {"profile_id": raw_prof or "general", "label": None}

    buckets = {"ok": [], "not_applicable": [], "not_evaluable": []}
    total = 0
    for cat, items in R.items():
        for k, e in (items or {}).items():
            total += 1
            st = (e or {}).get("status")
            if (e or {}).get("value") is None:
                st = st or "not_evaluable"
                buckets.setdefault(st, []).append((cat, k, e))
            else:
                buckets["ok"].append((cat, k, e))

    print("=" * 74)
    print(f"覆盖度自检：{path}")
    print(f"期间 {d.get('period', {}).get('current')} vs {d.get('period', {}).get('previous')}"
          f"　行业剖面：{prof.get('profile_id') or 'general'}"
          f"（{prof.get('label') or '通用档'}）"
          f"　来源：{prof.get('resolved_from') or '—'}")
    print("=" * 74)

    for cat, items in R.items():
        n = len(items or {})
        if not n:
            continue
        na = sum(1 for v in (items or {}).values() if (v or {}).get("status") == "not_applicable")
        ne = sum(1 for v in (items or {}).values()
                 if (v or {}).get("value") is None and (v or {}).get("status") != "not_applicable")
        mark = ""
        if na:
            mark += f"　不适用 {na}"
        if ne:
            mark += f"　⚠ 缺失 {ne}"
        print(f"  {CAT_LABEL.get(cat, cat):10s} {n:3d} 个{mark}")

    print("-" * 74)
    nok = len(buckets["ok"])
    nna = len(buckets["not_applicable"])
    nne = len(buckets["not_evaluable"])
    print(f"  总计 {total} 个　|　已算出 {nok}　|　行业不适用 {nna}　|　输入缺失 {nne}")
    if total:
        print(f"  有效覆盖率（不含主动跳过的）："
              f"{100 * nok / max(total - nna, 1):.0f}%")

    # ---- 三表勾稽自检结果 ---- #
    ck = d.get("checks") or {}
    ksum = ck.get("summary") or {}
    if ksum:
        print()
        print("  【三表勾稽自检】")
        print(f"    结论：{ck.get('overall')}　|　检查项 {ksum.get('total', 0)}"
              f"　平衡 {ksum.get('balanced', 0)}"
              f"　不平 {ksum.get('imbalanced', 0)}"
              f"　无法勾稽 {ksum.get('not_evaluable', 0)}")
        bad = [x for x in (ck.get("items") or []) if x.get("status") == "imbalanced"]
        for x in bad:
            print(f"      ⚠ {x.get('name')}（{x.get('period')}）"
                  f"差异 {x.get('diff'):,.0f} 元，占基准 {(x.get('diff_pct') or 0) * 100:.2f}%")
        if bad:
            print("      → 勾稽不平说明抽取结果内部不一致，需回到 A 核对口径与页码；B 不自动修正。")

    if nna:
        print()
        print("  【为什么会有「不适用」】")
        if prof.get("profile_id") == "banking":
            print("    当前是银行业剖面。银行不划分流动/非流动资产、没有应收/存货科目、")
            print("    利息支出是主营成本而非财务费用——因此毛利率、DSO、DIO、流动比率、")
            print("    利息保障倍数、自由现金流等 36 个制造业口径指标在银行语境下不成立。")
            print("    引擎主动跳过并标记 not_applicable，而不是拿空数据算出一个错误数字，")
            print("    更不是默认成「无风险」。这些维度改由 13 条银行业专属规则（B01–B13）刻画：")
            print("    NIM / 净利差 / 不良率 / 拨备覆盖率 / 资本充足率三级 / 存贷比 / 信用成本。")
        else:
            print("    当前行业剖面把部分指标判定为口径不成立，已主动跳过。")
        print()
        print("    被跳过的指标（示例）：")
        for cat, k, e in buckets["not_applicable"][:12]:
            print(f"      - {cat}.{k}")
        if len(buckets["not_applicable"]) > 12:
            print(f"      ... 其余 {len(buckets['not_applicable']) - 12} 个见输出 JSON 的 ratios 段")

    if nne:
        print()
        print("  【⚠ 这些是真缺数据，需要补】")
        for cat, k, e in buckets["not_evaluable"]:
            inputs = (e or {}).get("inputs") or {}
            miss = [kk for kk, vv in inputs.items() if vv is None]
            print(f"      - {cat}.{k}　缺：{', '.join(miss) if miss else '分母为 0'}")
            for m in miss:
                if m in FIELD_ADVICE:
                    print(f"          → {FIELD_ADVICE[m]}")

    print()
    return {"path": path, "total": total, "ok": nok,
            "not_applicable": nna, "not_evaluable": nne}


def main():
    ap = argparse.ArgumentParser(description="FinRadar · 指标覆盖度自检")
    ap.add_argument("target", nargs="?", help="output_ratios.json 路径")
    ap.add_argument("--all", action="store_true", help="检查工作区里所有 output_ratios.json")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    targets: list[str] = []
    if args.all:
        targets = sorted(glob.glob(os.path.join(ROOT, "**", "output_ratios.json"),
                                   recursive=True))
        targets = [os.path.relpath(t, ROOT) for t in targets]
    elif args.target:
        targets = [args.target]
    else:
        ap.error("请给出 JSON 路径，或使用 --all")

    if not targets:
        print("未找到任何 output_ratios.json")
        sys.exit(1)

    results = [check(t, args.verbose) for t in targets]

    if len(results) > 1:
        print("=" * 74)
        print("汇总")
        print("-" * 74)
        for r in results:
            print(f"  {r['path']:52s} {r['ok']:3d}/{r['total']:3d}"
                  f"　不适用 {r['not_applicable']:2d}　缺失 {r['not_evaluable']:2d}")


if __name__ == "__main__":
    main()
