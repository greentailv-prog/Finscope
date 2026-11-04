#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calibrate.py
============
用同业样本校准行业剖面里的阈值基准（`benchmarks.values`）。

为什么样本来源不是 C
--------------------
C 的估值可比池输出的是 `pe / pb / ps / ev_ebitda / revenue_growth /
gross_margin / ebitda_margin / market_cap`，全部是估值倍数与少量利润率。
不良率、拨备覆盖率、净利息收益率、资本充足率这些风险指标，估值倍数推不出来。
所以风险阈值的样本池只能由 B 自己维护——和多公司风险矩阵共用同一批结构化年报数据。

输入形态（二选一）
------------------
1) values      : 逐家公司原始值，脚本自己算分位数（推荐，可逐家复核）
2) percentiles : 外部已算好的 p10/p25/median/p75/p90 + n（必须带 source）

输出
----
只写 `benchmarks`，不动 `regulatory_basis`，也不改 `rule_overrides` 里的任何阈值。
阈值怎么用，由规则自己引用 `{metric}_industry_pXX` 决定（见 detect_risks.py 的 ctx 注入）。
每个指标标注状态：
    calibrated   n >= 15，可称"行业校准"
    indicative   5 <= n < 15，只能称"方向性参考"
    missing      样本不足，不得声称已校准

用法
----
    python3 calibrate.py --industry banking                 # 预演，不写盘
    python3 calibrate.py --industry banking --write          # 写回剖面
    python3 calibrate.py --self-test                         # 自检
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

MIN_CALIBRATED_N = 15
MIN_INDICATIVE_N = 5
QUANTILES = (("p10", 0.10), ("p25", 0.25), ("median", 0.50),
             ("p75", 0.75), ("p90", 0.90))


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #
def percentile(sorted_vals: list, q: float):
    """线性插值分位数（与 numpy 默认口径一致）。输入须已升序。"""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    frac = pos - lo
    return float(sorted_vals[lo]) + (float(sorted_vals[hi]) - float(sorted_vals[lo])) * frac


def status_of(n: int) -> str:
    if n >= MIN_CALIBRATED_N:
        return "calibrated"
    if n >= MIN_INDICATIVE_N:
        return "indicative"
    return "missing"


def summarize_values(raw: list) -> tuple[list, int]:
    """把 values 里的元素统一成数字，返回 (升序列表, 有效样本数)。"""
    vals = []
    for item in raw:
        v = item.get("value") if isinstance(item, dict) else item
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.append(float(v))
    vals.sort()
    return vals, len(vals)


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
class CalibrationError(ValueError):
    pass


def validate_percentiles(p: dict, metric: str) -> None:
    seq = []
    for key, _ in QUANTILES:
        v = p.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise CalibrationError(f"{metric}: 缺少或非法的 {key} = {v!r}")
        seq.append(float(v))
    for a, b, ka, kb in zip(seq, seq[1:], [k for k, _ in QUANTILES],
                            [k for k, _ in QUANTILES][1:]):
        if a > b:
            raise CalibrationError(f"{metric}: 分位数不单调，{ka}={a} > {kb}={b}")


# --------------------------------------------------------------------------- #
# 样本读取
# --------------------------------------------------------------------------- #
def build_metric(spec: dict, metric: str, default_source: str, default_as_of: str) -> dict:
    if "values" in spec:
        vals, n = summarize_values(spec["values"])
        if n == 0:
            raise CalibrationError(f"{metric}: values 为空或全部非数值")
        out = {key: round(percentile(vals, q), 8) for key, q in QUANTILES}
    elif "percentiles" in spec:
        out = {k: (round(float(v), 8) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
               for k, v in spec["percentiles"].items()}
        n = spec.get("n")
        if not isinstance(n, int) or n <= 0:
            raise CalibrationError(f"{metric}: percentiles 模式必须给出正整数 n")
        validate_percentiles(out, metric)
    else:
        raise CalibrationError(f"{metric}: 需要 values 或 percentiles 之一")

    out["n"] = n
    out["status"] = status_of(n)
    out["unit"] = spec.get("unit") or "ratio"
    out["source"] = spec.get("source") or default_source
    out["as_of"] = spec.get("as_of") or default_as_of
    return out


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def calibrate(profile: dict, samples: dict) -> tuple[dict, list]:
    bm = profile.setdefault("benchmarks", {})
    values = bm.setdefault("values", {})

    default_source = samples.get("sample_definition") or samples.get("source") or ""
    default_as_of = samples.get("as_of") or bm.get("as_of") or ""

    rows = []
    for metric, spec in (samples.get("metrics") or {}).items():
        new = build_metric(spec, metric, default_source, default_as_of)
        old = values.get(metric) or {}
        old_status = old.get("status") or ("calibrated" if bm.get("calibrated") and old.get("n") else "missing")
        values[metric] = new
        rows.append({
            "metric": metric,
            "old_status": old_status,
            "new_status": new["status"],
            "n": new["n"],
            "unit": new["unit"],
            "values": {k: new[k] for k, _ in QUANTILES},
            "source": new["source"],
        })

    # 样本里没有、剖面里已存在的指标，按样本量补状态，不篡改数值
    for metric, spec in values.items():
        if not isinstance(spec, dict) or "status" in spec:
            continue
        n = spec.get("n")
        spec["status"] = status_of(n) if isinstance(n, int) else "missing"

    required = list(values.keys())
    calibrated = [m for m in required if values[m].get("status") == "calibrated"]
    indicative = [m for m in required if values[m].get("status") == "indicative"]
    missing = [m for m in required if values[m].get("status") == "missing"]

    bm["as_of"] = default_as_of
    bm["source"] = default_source or bm.get("source")
    bm["calibrated"] = bool(required) and len(calibrated) == len(required)
    bm["calibrated_metrics"] = calibrated
    bm["indicative_metrics"] = indicative
    bm["missing_metrics"] = missing
    bm["coverage"] = (round(len(calibrated) / len(required), 4) if required else 0.0)
    bm["sample_definition"] = samples.get("sample_definition")

    return profile, rows


# --------------------------------------------------------------------------- #
# 展示
# --------------------------------------------------------------------------- #
def fmt(v, unit: str) -> str:
    if v is None:
        return "—"
    if unit in ("ratio", "pct", "percent"):
        return f"{v * 100:.2f}%"
    if unit in ("days", "day"):
        return f"{v:.1f}天"
    return f"{v:,.4g}"


def print_report(rows: list, bm: dict, industry: str) -> None:
    print()
    print(f"行业剖面：{industry}")
    print(f"样本口径：{bm.get('sample_definition') or '—'}")
    print(f"截至日期：{bm.get('as_of') or '—'}")
    print()
    head = f"{'指标':<28}{'n':>4}  {'状态':<11}{'p10':>10}{'p25':>10}{'median':>10}{'p75':>10}{'p90':>10}"
    print(head)
    print("-" * len(head.encode("gbk", errors="ignore")))
    for r in rows:
        v = r["values"]
        print(f"{r['metric']:<28}{r['n']:>4}  {r['new_status']:<11}"
              f"{fmt(v['p10'], r['unit']):>10}{fmt(v['p25'], r['unit']):>10}"
              f"{fmt(v['median'], r['unit']):>10}{fmt(v['p75'], r['unit']):>10}"
              f"{fmt(v['p90'], r['unit']):>10}")
    print()
    print(f"已校准 {len(bm['calibrated_metrics'])} 项 / 方向性 {len(bm['indicative_metrics'])} 项 "
          f"/ 样本不足 {len(bm['missing_metrics'])} 项　覆盖度 {bm['coverage']:.0%}")
    if bm["missing_metrics"]:
        print(f"样本不足：{'、'.join(bm['missing_metrics'])}")
    print()
    print("注意：分位数只回答「同业处在什么水平」，不能替代监管红线。"
          "资本充足率、拨备覆盖率、LCR/NSFR 的阈值必须引用法规条文。")


# --------------------------------------------------------------------------- #
# 自检
# --------------------------------------------------------------------------- #
def self_test() -> None:
    def expect(cond, msg):
        if not cond:
            raise AssertionError(msg)

    series = list(range(1, 11))
    expect(percentile(series, 0.50) == 5.5, "p50 应为 5.5")
    expect(abs(percentile(series, 0.25) - 3.25) < 1e-12, "p25 应为 3.25")
    expect(abs(percentile(series, 0.10) - 1.9) < 1e-12, "p10 应为 1.9")
    expect(percentile([7], 0.9) == 7.0, "单样本应返回自身")

    expect(status_of(20) == "calibrated", "n=20 应为 calibrated")
    expect(status_of(15) == "calibrated", "n=15 应为 calibrated")
    expect(status_of(14) == "indicative", "n=14 应为 indicative")
    expect(status_of(4) == "missing", "n=4 应为 missing")

    good = {"p10": 0.03, "p25": 0.04, "median": 0.05, "p75": 0.06, "p90": 0.07}
    validate_percentiles(good, "ok")
    bad = {"p10": 0.08, "p25": 0.04, "median": 0.05, "p75": 0.06, "p90": 0.07}
    try:
        validate_percentiles(bad, "bad")
    except CalibrationError:
        pass
    else:
        raise AssertionError("非单调分位数应被拒绝")

    m = build_metric({"values": [{"company": "x", "value": 0.1},
                                 {"company": "y", "value": 0.3}], "unit": "ratio"},
                     "t", "src", "2026-01-01")
    expect(m["n"] == 2 and m["status"] == "missing", "2 个样本应为 missing")
    expect(abs(m["median"] - 0.2) < 1e-12, "两样本中位数应为 0.2")

    print("[OK] 自检通过：分位数插值、状态分档、单调校验、样本汇总均符合预期")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="用同业样本校准行业剖面的阈值基准")
    ap.add_argument("--industry", help="行业剖面 id，如 banking")
    ap.add_argument("--samples", default=None, help="样本文件（默认 data/peer_samples/<industry>.json）")
    ap.add_argument("--profile-dir", default=None, help="剖面目录（默认 ../data/industry_profiles）")
    ap.add_argument("--write", action="store_true", help="写回剖面；不给则只预演")
    ap.add_argument("--self-test", action="store_true", help="运行内置自检")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.industry:
        ap.error("需要 --industry（或使用 --self-test）")

    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.dirname(here)
    profile_dir = args.profile_dir or os.path.join(base, "data", "industry_profiles")
    samples_path = args.samples or os.path.join(base, "data", "peer_samples",
                                                f"{args.industry}.json")
    profile_path = os.path.join(profile_dir, f"{args.industry}.json")

    for p in (samples_path, profile_path):
        if not os.path.exists(p):
            sys.exit(f"[ERR] 找不到文件：{p}")

    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    with open(samples_path, encoding="utf-8") as f:
        samples = json.load(f)

    before = json.dumps(profile.get("benchmarks") or {}, sort_keys=True, ensure_ascii=False)

    try:
        profile, rows = calibrate(profile, samples)
    except CalibrationError as e:
        sys.exit(f"[ERR] 校准失败：{e}")

    bm = profile["benchmarks"]
    print_report(rows, bm, args.industry)

    after = json.dumps(bm, sort_keys=True, ensure_ascii=False)
    if before == after:
        print("剖面无变化（样本与现有基准一致）。")
        return

    if args.write:
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[OK] 已写回 {profile_path}")
    else:
        print("（预演模式，未写盘。确认无误后加 --write）")


if __name__ == "__main__":
    main()
