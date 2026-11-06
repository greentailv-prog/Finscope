#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作台链路自检：按 D 的六步调用顺序跑一遍，验证 B 的入口没有断。

D 的调用约定（`给B的三点确认` 第 ③ 节）：

    1. D 写 b_input.json（顶层含 peer_financials）
    2. compute_ratios.py -i b_input.json -o b_ratios.json
    3. D 给每个 peer 写 peer_inputs/<ticker>.json
    4. compute_ratios.py -i peer_inputs/<ticker>.json -o peer_ratios/<ticker>.json
    5. build_comparison.py --target b_ratios.json --peers peer_ratios --out comparison.json
    6. detect_risks.py --ratios b_ratios.json --comparison comparison.json -o b_risks.json

本脚本把第 2–6 步串起来，第 3 步由本脚本代做（模拟 D 的拆分），用来回答一个问题：
「这份 b_input 喂进来，B 能不能一路跑到风险卡，阈值是当次同业还是回退了固定值」。

用法：
    python3 scripts_link_check.py --b-input /path/b_input.json
    python3 scripts_link_check.py --b-input /path/b_input.json --out-dir /tmp/link --strict

`--strict` 下，任何一步非零退出即中止；默认也会中止，`--keep-going` 才继续跑完看全局。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPUTE = os.path.join(ROOT, "financial-diagnosis", "scripts", "compute_ratios.py")
COMPARE = os.path.join(ROOT, "risk-radar", "scripts", "build_comparison.py")
DETECT = os.path.join(ROOT, "risk-radar", "scripts", "detect_risks.py")
RULES = os.path.join(ROOT, "risk-radar", "risk_rules.json")


def step(no: int, title: str) -> None:
    print("\n[%d/6] %s" % (no, title))


def run(cmd: list, log_path: str) -> tuple:
    with open(log_path, "w", encoding="utf-8") as f:
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    tail = ""
    try:
        with open(log_path, encoding="utf-8") as f:
            lines = [x for x in f.read().splitlines() if x.strip()]
        tail = lines[-1][:100] if lines else ""
    except OSError:
        pass
    return p.returncode, tail


def main() -> int:
    ap = argparse.ArgumentParser(description="B 侧工作台链路自检（按 D 的六步调用顺序）")
    ap.add_argument("--b-input", required=True, help="D 写出的 b_input.json（顶层可含 peer_financials）")
    ap.add_argument("--out-dir", default=None, help="中间产物目录，默认 <b_input 所在目录>/_link_check")
    ap.add_argument("--rules", default=RULES, help="风险规则文件")
    ap.add_argument("--keep-going", action="store_true", help="某步失败仍继续跑完，便于一次看全")
    ap.add_argument("--same-industry", action="store_true",
                    help="要求同业剖面一致（默认可跨行业，联调样本常混行业）")
    args = ap.parse_args()

    if not os.path.exists(args.b_input):
        print("[FAIL] 找不到 b_input：%s" % args.b_input, file=sys.stderr)
        return 2
    raw = json.load(open(args.b_input, encoding="utf-8"))
    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(args.b_input)), "_link_check")
    peer_inputs = os.path.join(out_dir, "peer_inputs")
    peer_ratios = os.path.join(out_dir, "peer_ratios")
    for d in (out_dir, peer_inputs, peer_ratios):
        os.makedirs(d, exist_ok=True)

    print("b_input：%s" % args.b_input)
    print("公司：%s（%s）｜期间：%s" % (
        (raw.get("company") or {}).get("name"),
        (raw.get("company") or {}).get("ticker"),
        (raw.get("meta") or {}).get("periods")))
    peers = raw.get("peer_financials") or []
    print("同业：%d 家%s" % (len(peers), "" if peers else "（空数组 → 应回退固定阈值，不是报错）"))

    b_ratios = os.path.join(out_dir, "b_ratios.json")
    comparison = os.path.join(out_dir, "comparison.json")
    b_risks = os.path.join(out_dir, "b_risks.json")
    fails = []

    step(2, "目标公司指标：compute_ratios -i b_input.json")
    rc, tail = run([sys.executable, COMPUTE, "-i", args.b_input, "-o", b_ratios, "--pretty"],
                   os.path.join(out_dir, "step2_compute.log"))
    print("     退出 %d %s" % (rc, ("｜" + tail) if tail else ""))
    if rc != 0:
        fails.append("第 2 步：目标公司指标算不出来")
        if not args.keep_going:
            return _report(fails, out_dir, None, None)

    step(3, "拆分 peer_financials → peer_inputs/<ticker>.json（D 的动作，本脚本代做）")
    if not os.path.exists(b_ratios):
        fails.append("第 3 步：缺 b_ratios，无法继续")
        return _report(fails, out_dir, None, None)
    written = 0
    for item in peers:
        c = item.get("company") or {}
        code = c.get("ticker") or ("peer%d" % written)
        # 只写 company + financials：D 的示例里 peer 条目没有 meta，
        # 这里刻意照做，验证 compute_ratios 能靠 financials 自行推断期间。
        json.dump({"company": c, "financials": item.get("financials") or {}},
                  open(os.path.join(peer_inputs, "%s.json" % code), "w", encoding="utf-8"),
                  ensure_ascii=False)
        written += 1
    print("     写出 %d 份（不含 meta.periods，按 D 的示例结构）" % written)

    step(4, "同业指标：逐个 compute_ratios")
    peer_ok = 0
    for fn in sorted(os.listdir(peer_inputs)):
        code = fn[:-5]
        rc, tail = run([sys.executable, COMPUTE, "-i", os.path.join(peer_inputs, fn),
                        "-o", os.path.join(peer_ratios, fn)],
                       os.path.join(out_dir, "step4_%s.log" % code))
        print("     %-10s 退出 %d %s" % (code, rc, ("｜" + tail[:60]) if rc and tail else ""))
        if rc == 0:
            peer_ok += 1
    if written and peer_ok < written:
        fails.append("第 4 步：%d 家同业里有 %d 家算失败" % (written, written - peer_ok))

    step(5, "同业对比：build_comparison --peers peer_ratios")
    cmd = [sys.executable, COMPARE, "--target", b_ratios, "--peers", peer_ratios,
           "--out", comparison]
    if not args.same_industry:
        cmd.append("--allow-cross-industry")
    rc, tail = run(cmd, os.path.join(out_dir, "step5_compare.log"))
    print("     退出 %d %s" % (rc, ("｜" + tail) if tail else ""))
    if rc != 0:
        fails.append("第 5 步：同业对比失败")

    step(6, "风险判定：detect_risks --comparison")
    rc, tail = run([sys.executable, DETECT, "--ratios", b_ratios, "--rules", args.rules,
                    "--comparison", comparison, "-o", b_risks, "--pretty"],
                   os.path.join(out_dir, "step6_detect.log"))
    print("     退出 %d %s" % (rc, ("｜" + tail) if tail else ""))
    if rc != 0:
        fails.append("第 6 步：风险判定失败")

    return _report(fails, out_dir, comparison, b_risks)


def _report(fails: list, out_dir: str, comparison: str, b_risks: str) -> int:
    print("\n" + "=" * 66)
    if comparison and os.path.exists(comparison):
        c = json.load(open(comparison, encoding="utf-8"))
        print("comparison：status=%s  同业 %s 家  阈值项 %d" % (
            c.get("status"), c.get("sample_n"), len(c.get("thresholds") or {})))
        ps = c.get("peer_set") or []
        if ps:
            print("peer_set：%s" % "、".join("%s(%s)" % (p.get("ticker"), p.get("ticker_full")) for p in ps))
    if b_risks and os.path.exists(b_risks):
        d = json.load(open(b_risks, encoding="utf-8"))
        cards = d.get("risks") or []
        import collections
        cnt = collections.Counter(x.get("threshold_source") for x in cards)
        peer_n = sum(v for k, v in cnt.items() if str(k).startswith("peer_"))
        ind_n = sum(v for k, v in cnt.items() if str(k).startswith("industry_"))
        fb_n = cnt.get("fixed_fallback", 0)
        print("风险卡：%d 张｜当次同业阈值 %d 条｜离线基准 %d 条｜回退固定 %d 条" % (
            len(cards), peer_n, ind_n, fb_n))
        for x in cards:
            if str(x.get("threshold_source", "")).startswith(("peer_", "industry_")):
                print("   %-4s %-14s %-12s 样本 %s  %s" % (
                    x.get("risk_id"), x.get("threshold_source"),
                    ("%.4f" % x["threshold_value"]) if isinstance(x.get("threshold_value"), float) else x.get("threshold_value"),
                    x.get("peer_sample_n"), x.get("status")))
        if not peer_n:
            print("   提示：没有一条用到当次同业分位——同业不足 3 家，或该规则未声明动态阈值")
    print("产物目录：%s" % out_dir)
    if fails:
        print("\n[FAIL] 链路有断点：")
        for f in fails:
            print("  - " + f)
        return 1
    print("\n[OK] 链路通：b_input → 指标 → 同业对比 → 风险卡，退出码全 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
