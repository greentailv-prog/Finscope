#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同业对比：目标公司 vs 可比公司，输出 comparison 结构（规范 §6.4）。

输入是若干个 ratios 输出 JSON（目标公司 + 同业）。输出三块：

- `metrics`：逐指标的目标值、同业中位数 / P25 / P75、目标分位、样本量
- `risk_matrix`：成长 / 盈利 / 偿债 / 营运 / 现金流 五维，各给目标 vs 同业
- `thresholds`：给 5 条规则的同业阈值建议（P75 / P25 + 样本量）

三条原则：
1. **样本不足不下结论。** n<3 时 `status="partial"`，只给数值，不写"显著高于/低于"。
2. **不给 0–100 的假评分。** 五维只给相对位置（高 / 中 / 低）与分位。
3. **同行业才可比。** 目标与同业的 `industry_profile` 不一致直接报错退出。

用法：
    python3 build_comparison.py --target r_600519.json --peers peers/ --out comparison.json
    python3 build_comparison.py --target r_600519.json --out comparison.json   # 无同业，输出 not_available
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
import sys

MIN_SAMPLE = 3          # 少于 3 家只出 partial
FULL_SAMPLE = 5         # 5 家以上才敢说"同业水平"

# 参与对比的指标：metric 键 → (中文名, 取值路径, 越高越好)
METRICS = [
    ("revenue_growth", "营业收入增速", ("growth", "revenue_growth"), True),
    ("gross_margin", "毛利率", ("profitability", "gross_margin"), True),
    ("net_margin_parent", "归母净利率", ("profitability", "net_margin_parent"), True),
    ("roe", "净资产收益率", ("profitability", "roe"), True),
    ("debt_to_assets", "资产负债率", ("solvency", "debt_to_assets"), False),
    ("dso", "应收账款周转天数", ("efficiency", "dso"), False),
    ("dio", "存货周转天数", ("efficiency", "dio"), False),
    ("ocf_to_net_income", "净现比", ("cashflow_quality", "ocf_to_net_income"), True),
]

# 动态阈值用的派生对比量：键 → (中文名, 表达式, 方向)
# 只对规范点名的 5 条规则做，其余一律 fixed。
THRESHOLD_METRICS = {
    "ar_growth_gap": ("应收增速 − 收入增速", "accounts_receivable_growth - revenue_growth", "p75"),
    "inventory_growth_gap": ("存货增速 − 成本增速", "inventory_growth - cost_of_revenue_growth", "p75"),
    "gross_margin": ("毛利率", "gross_margin", "p25"),
    "dso_delta": ("应收周转天数变动", "dso_delta", "p75"),
    "debt_to_assets": ("资产负债率", "debt_to_assets", "p75"),
}

# 五维矩阵：维度 → (指标列表, 说明)
DIMENSIONS = [
    ("成长", ["revenue_growth"], "收入增速相对同业的位置"),
    ("盈利", ["gross_margin", "net_margin_parent", "roe"], "毛利率、净利率、ROE 的综合位置"),
    ("偿债", ["debt_to_assets"], "资产负债率越低越稳健"),
    ("营运", ["dso", "dio"], "周转天数越短效率越高"),
    ("现金流", ["ocf_to_net_income"], "利润的现金转化能力"),
]


# --------------------------------------------------------------------------- #
# 取值与统计
# --------------------------------------------------------------------------- #
def ratio_value(diag: dict, cat: str, key: str):
    rec = ((diag.get("ratios") or {}).get(cat) or {}).get(key) or {}
    v = rec.get("value")
    return float(v) if isinstance(v, (int, float)) else None


def ratio_delta(diag: dict, cat: str, key: str):
    rec = ((diag.get("ratios") or {}).get(cat) or {}).get(key) or {}
    v = rec.get("delta")
    return float(v) if isinstance(v, (int, float)) else None


def expr_value(diag: dict, expr: str):
    """按 THRESHOLD_METRICS 的表达式取当期值。只支持已登记的几种形式。"""
    r = diag.get("ratios") or {}
    if expr == "gross_margin":
        return ratio_value(diag, "profitability", "gross_margin")
    if expr == "debt_to_assets":
        return ratio_value(diag, "solvency", "debt_to_assets")
    if expr == "dso_delta":
        return ratio_delta(diag, "efficiency", "dso")
    if expr == "accounts_receivable_growth - revenue_growth":
        a = ratio_value(diag, "efficiency", "accounts_receivable_growth")
        b = ratio_value(diag, "growth", "revenue_growth")
        return None if (a is None or b is None) else a - b
    if expr == "inventory_growth - cost_of_revenue_growth":
        a = ratio_value(diag, "efficiency", "inventory_growth")
        b = ratio_value(diag, "growth", "cost_of_revenue_growth")
        return None if (a is None or b is None) else a - b
    return None


def percentile(sorted_vals, q):
    """线性插值分位数（与 calibrate.py 同一实现，避免两处口径不同）。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def pct_rank(vals, x):
    """x 在 vals 中的分位（0–1），用中位秩，避免小样本极值卡在 0 或 1。"""
    if x is None or not vals:
        return None
    below = sum(1 for v in vals if v < x)
    equal = sum(1 for v in vals if v == x)
    return (below + 0.5 * equal) / len(vals)


def _flag(target, p25, p75, better_high):
    if target is None or p25 is None or p75 is None:
        return None
    if better_high:
        return "above_p75" if target > p75 else ("below_p25" if target < p25 else "in_range")
    return "worse_than_p75" if target > p75 else ("better_than_p25" if target < p25 else "in_range")


# --------------------------------------------------------------------------- #
# 主逻辑
# --------------------------------------------------------------------------- #
def build(target: dict, peers: list, peer_meta: list) -> dict:
    t_profile = target.get("industry_profile")
    years = set()

    rows = []
    for metric, label, (cat, key), better_high in METRICS:
        tv = ratio_value(target, cat, key)
        pv = [v for v in (ratio_value(p, cat, key) for p in peers) if v is not None]
        pv_sorted = sorted(pv)
        p25 = percentile(pv_sorted, 0.25)
        p50 = percentile(pv_sorted, 0.50)
        p75 = percentile(pv_sorted, 0.75)
        rows.append({
            "metric": metric,
            "label": label,
            "target": tv,
            "peer_median": p50,
            "peer_p25": p25,
            "peer_p75": p75,
            "percentile": pct_rank(pv, tv),
            "sample_n": len(pv),
            "better": "higher" if better_high else "lower",
            "flag": _flag(tv, p25, p75, better_high),
        })

    # ---- 动态阈值建议 ---- #
    thresholds = {}
    for mkey, (label, expr, basis) in THRESHOLD_METRICS.items():
        vals = [v for v in (expr_value(p, expr) for p in peers) if v is not None]
        vals_sorted = sorted(vals)
        q = 0.75 if basis == "p75" else 0.25
        thresholds[mkey] = {
            "label": label,
            "basis": "peer_" + basis,
            "value": percentile(vals_sorted, q),
            "sample_n": len(vals),
            "expr": expr,
        }

    # ---- 五维矩阵 ---- #
    by_metric = {r["metric"]: r for r in rows}
    matrix = []
    for dim, mlist, note in DIMENSIONS:
        parts = [by_metric[m] for m in mlist if m in by_metric and by_metric[m]["percentile"] is not None]
        if not parts:
            matrix.append({"dimension": dim, "target_level": None, "peer_level": "中",
                           "note": "同业数据不足，本维度不做判断", "metrics": mlist})
            continue
        # 质量分：越高越好取分位，越低越好取 1−分位
        q = sum((r["percentile"] if r["better"] == "higher" else 1 - r["percentile"]) for r in parts) / len(parts)
        level = "高" if q >= 0.60 else ("低" if q < 0.35 else "中")
        matrix.append({
            "dimension": dim,
            "target_level": level,
            "peer_level": "中",           # 同业分位的中位数按定义为中
            "quality_percentile": round(q, 4),
            "note": note,
            "metrics": mlist,
        })

    n_min = min([r["sample_n"] for r in rows] or [0])
    status = "not_available" if not peers else ("ok" if n_min >= MIN_SAMPLE else "partial")

    # 可比性自评：行业字段缺失时，剖面相同不等于真的同行业。
    # 不写这一条，读者会把"茅台 vs 比亚迪"当成同业对比。
    inds = [(p.get("company") or {}).get("industry") for p in peers]
    untagged = sum(1 for x in inds if not x)
    if t_profile in (None, "", "general"):
        comparability = {"level": "weak",
                         "note": "行业剖面未识别（%s），同业只在同一剖面内可比，不能当作严格同行业对比" % t_profile}
    elif untagged:
        comparability = {"level": "partial",
                         "note": "%d 家同业缺少行业字段，可比性需人工确认" % untagged}
    else:
        comparability = {"level": "ok", "note": "目标与同业行业字段一致，按同行业口径对比"}

    return {
        "schema": "finradar.comparison/1.0",
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "risk-radar/scripts/build_comparison.py",
        "status": status,
        "comparability": comparability,
        "industry_profile": t_profile,
        "target": {
            "ticker": (target.get("company") or {}).get("ticker"),
            "name": (target.get("company") or {}).get("name"),
            "report_period": (target.get("period") or {}).get("current"),
        },
        "peer_set": peer_meta,
        "sample_n": len(peers),
        "metrics": rows,
        "risk_matrix": matrix,
        "thresholds": thresholds,
        "notes": {
            "status_rule": "同业 %d 家及以上才标 ok；1–2 家标 partial；没有同业标 not_available" % MIN_SAMPLE,
            "no_fake_score": "五维只给相对位置（高/中/低）与质量分位，不给 0–100 评分",
            "peers_not_selected_here": "同业名单由 C 决定，本脚本只算分位与位置，不自己选同业",
        },
    }


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="同业对比（规范 §6.4）")
    ap.add_argument("--target", required=True, help="目标公司的 ratios JSON")
    ap.add_argument("--peers", nargs="*", default=[],
                    help="同业 ratios JSON 文件或目录；不传或目录为空时输出 status=not_available，退出码 0")
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-cross-industry", action="store_true",
                    help="允许跨行业对比（默认拒绝）")
    args = ap.parse_args()

    target = load(args.target)
    files = []
    for p in (args.peers or []):
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(p, "*.json"))))
        else:
            files.append(p)
    files = [f for f in files if os.path.abspath(f) != os.path.abspath(args.target)]
    if not files:
        # 规范 §6.4 / §10.2：没有同业不是错误，降级为 not_available，不中断整条链路。
        out = build(target, [], [])
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("[OK] comparison -> %s" % args.out)
        print("     status=not_available（未提供同业，全部指标与阈值置空，规则回退固定阈值）")
        return 0

    peers, meta = [], []
    for f in files:
        d = load(f)
        prof = d.get("industry_profile")
        if not args.allow_cross_industry and prof != target.get("industry_profile"):
            print("[FAIL] 行业剖面不一致：目标 %s，%s 是 %s。同业对比只能在同行业内做。"
                  % (target.get("industry_profile"), os.path.basename(f), prof), file=sys.stderr)
            return 1
        peers.append(d)
        c = d.get("company") or {}
        meta.append({
            "ticker": c.get("ticker"),
            # D 要求 peer_set 的代码能和 C 的 valuation.comps.peer_companies 对上；
            # C 用带后缀全码，B 的 ticker 按约定恒为 6 位，所以在这里透传 ticker_full，
            # 让 D 直接匹配，不必自己拼后缀（拼错市场后缀比不匹配更糟）。
            "ticker_full": c.get("ticker_full"),
            "exchange_code": c.get("exchange_code"),
            "name": c.get("name"),
            "report_period": (d.get("period") or {}).get("current"),
        })

    out = build(target, peers, meta)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("[OK] comparison -> %s" % args.out)
    print("     status=%s  同业 %d 家  行业=%s" % (out["status"], len(peers), out["industry_profile"]))
    for r in out["metrics"]:
        def fmt(v, m):
            if v is None:
                return "—"
            return ("%.1f 天" % v) if m in ("dso", "dio") else ("%.2f%%" % (v * 100))
        print("     %-18s 目标 %9s  P25 %9s  中位 %9s  P75 %9s  分位 %s  样本 %d"
              % (r["label"], fmt(r["target"], r["metric"]), fmt(r["peer_p25"], r["metric"]),
                 fmt(r["peer_median"], r["metric"]), fmt(r["peer_p75"], r["metric"]),
                 "—" if r["percentile"] is None else "%.0f%%" % (r["percentile"] * 100),
                 r["sample_n"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
