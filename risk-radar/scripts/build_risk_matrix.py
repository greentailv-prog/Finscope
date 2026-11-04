#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_risk_matrix.py
====================
把多家公司的风险诊断结果拼成一张可对比的矩阵。

为什么单独一个脚本
------------------
`detect_risks.py` 一次只吃一家公司，这是对的：单家诊断要保留完整证据链。
但"对比"是另一个动作，它需要的不是证据链，而是**同口径下的横向排列**。
硬把多公司塞进 detect_risks.py 会让单家逻辑变复杂，所以拆开。

一条硬规则：**只允许同一行业剖面内的公司进同一张矩阵**。
不同行业的风险阈值与指标适用性都不同，混在一张表里比较会得出错误结论
（本项目已实证：制造业口径套银行，触发 2 条全错、待核验从 2 涨到 66）。

输出里带两个现成的二维坐标，供下游画风险矩阵图或做排序，不必再解析明细：

- `risk_matrix_view.points`：每条规则一个点。x = 触发广度（触发家数/可评估家数），
  y = 触发强度（触发公司的平均风险分），气泡大小 = 触发家数。
  象限分界 `mid_x/mid_y` 取本批中位数——一批公司往往没有规则触发面过半，
  画固定 50% 线会让全部点挤在左边，触发最多的规则反而被读成「低频」。
  横轴衡量的是「同类公司里已触发的比例」，年报是已发生的事实，不是发生概率的预测。
- `company_view.points`：每家公司一个点。x = 触发规则占比，y = 综合风险分，
  气泡大小 = 不可评估规则数（越大结论越要打折看）。

每个触发格还带 `trigger_values`（指标实测值），下游能复算「超出阈值多少」，
不必解析结论文字。

用法
----
    python3 build_risk_matrix.py --diag-dir ../demo/matrix/ratios --rules ../risk_rules.json -o matrix.json
    python3 build_risk_matrix.py --diag a.json b.json c.json -o matrix.json
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detect_risks as DR  # noqa: E402

SCHEMA_VERSION = "finradar.risk-matrix/1.0"
DEFAULT_RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "risk_rules.json")


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def display_width(text: str) -> int:
    """中文按两格算，用于控制台对齐。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(text))


def pad(text, width: int, align: str = "left") -> str:
    text = str(text)
    gap = max(0, width - display_width(text))
    return (" " * gap + text) if align == "right" else (text + " " * gap)


def company_key(diag: dict) -> str:
    c = diag.get("company") or {}
    return str(c.get("ticker") or c.get("name") or "UNKNOWN")


def company_label(diag: dict) -> str:
    c = diag.get("company") or {}
    name = c.get("name") or "未命名"
    ticker = c.get("ticker")
    return f"{name}（{ticker}）" if ticker else str(name)


def collect_paths(args) -> list:
    paths = list(args.diag or [])
    if args.diag_dir:
        for p in sorted(glob.glob(os.path.join(args.diag_dir, "*.json"))):
            base = os.path.basename(p)
            if base.startswith("risk_matrix") or "output_risks" in base:
                continue
            paths.append(p)
    if not paths:
        sys.exit("[ERR] 没有输入：请给 --diag 或 --diag-dir")
    seen, out = set(), []
    for p in paths:
        ap = os.path.abspath(p)
        if ap in seen:
            continue
        seen.add(ap)
        out.append(ap)
    return out


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def build(paths: list, rules_doc: dict, industry: str | None,
          profile_dir: str | None, comparison_dir: str | None = None) -> dict:
    results = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            diag = json.load(f)
        hint = (diag.get("company") or {}).get("industry") or (diag.get("meta") or {}).get("industry")
        profile, _how = DR.load_profile(industry, hint, profile_dir)
        comp = None
        if comparison_dir:
            cpath = os.path.join(comparison_dir, os.path.splitext(os.path.basename(path))[0] + ".json")
            if os.path.exists(cpath):
                with open(cpath, encoding="utf-8") as f:
                    comp = json.load(f)
        res = DR.detect(diag, rules_doc, None, profile=profile, comparison=comp)
        results.append({"path": path, "diag": diag, "res": res, "profile": profile})

    # ---- 可比性守卫：同一行业剖面 ----
    profile_ids = {r["profile"]["profile_id"] for r in results}
    if len(profile_ids) > 1:
        detail = "\n".join(
            f"  - {company_label(r['diag'])} → {r['profile']['profile_id']}" for r in results)
        sys.exit("[ERR] 输入公司落在不同行业剖面，不能放进同一张矩阵：\n"
                 f"{detail}\n"
                 "请按行业拆分，或显式传 --industry 统一口径（同行业才允许）。")

    periods = sorted({str((r["diag"].get("period") or {}).get("current")) for r in results})
    profile0 = results[0]["profile"]

    # ---- 规则列顺序：以第一条结果的规则顺序为准 ----
    rule_cols = []
    for r in results[0]["res"]["risks"]:
        rule_cols.append({
            "risk_id": r["risk_id"],
            "risk_name": r["risk_name"],
            "category": r.get("category"),
            "category_label": r.get("category_label"),
            "severity": r.get("severity"),
        })
    known = {c["risk_id"] for c in rule_cols}
    for r in results:
        for item in r["res"]["risks"]:
            if item["risk_id"] not in known:
                known.add(item["risk_id"])
                rule_cols.append({
                    "risk_id": item["risk_id"],
                    "risk_name": item["risk_name"],
                    "category": item.get("category"),
                    "category_label": item.get("category_label"),
                    "severity": item.get("severity"),
                })

    companies, matrix = [], {}
    for r in results:
        key = company_key(r["diag"])
        if key in matrix:
            sys.exit(f"[ERR] 公司标识重复：{key}（检查 ticker / name）")
        cells = {}
        for item in r["res"]["risks"]:
            cells[item["risk_id"]] = {
                "status": item["status"],
                "severity": item.get("severity"),
                "severity_tag": item.get("severity_tag"),
                "score": item.get("score"),
                "explanation": item.get("explanation"),
                # 阈值来源要跟着进矩阵：否则读者不知道这一格是按固定阈值还是同业分位判的
                "threshold_value": item.get("threshold_value"),
                "threshold_source": item.get("threshold_source"),
                "peer_sample_n": item.get("peer_sample_n"),
            }
            # 实测值只对触发格有意义。放进矩阵是为了让下游能复算「超出阈值多少」，
            # 而不是只能读一句结论文字。
            if item["status"] == "triggered" and item.get("trigger_values"):
                cells[item["risk_id"]]["trigger_values"] = item["trigger_values"]
        matrix[key] = cells
        s = r["res"]["summary"]
        ck = (r["diag"].get("checks") or {})
        ck_sum = ck.get("summary") or {}
        # 勾稽不平 = 输入数据自身矛盾，此时风险分再高也不能直接下结论。
        # 把它做成独立字段，矩阵里跟风险分并列显示，读者一眼看出哪几行不可尽信。
        if ck_sum.get("imbalanced", 0) > 0:
            reliability, rel_note = "低", "勾稽不平 %d 项，指标与风险结论需先核对数据" % ck_sum["imbalanced"]
        elif ck_sum.get("not_evaluable", 0) > 0:
            reliability, rel_note = "中", "有 %d 项勾稽无法评估（缺科目或口径不成立）" % ck_sum["not_evaluable"]
        else:
            reliability, rel_note = "高", "各项勾稽均平衡"
        companies.append({
            "key": key,
            "name": (r["diag"].get("company") or {}).get("name"),
            "ticker": (r["diag"].get("company") or {}).get("ticker"),
            "period": (r["diag"].get("period") or {}).get("current"),
            "overall_risk_level": s["overall_risk_level"],
            "overall_risk_score": s["overall_risk_score"],
            "conclusion_reliability": reliability,
            "reliability_note": rel_note,
            # 数据质量：勾稽不平的公司，它的风险结论要打折看
            "data_quality": {
                "articulation": ck.get("overall"),
                "balanced": ck_sum.get("balanced", 0),
                "imbalanced": ck_sum.get("imbalanced", 0),
                "not_evaluable": ck_sum.get("not_evaluable", 0),
                "reviews_inherited": len(r["diag"].get("review_queue") or []),
            },
            "counts": {
                "triggered": s["triggered"],
                "high": s["by_severity"]["high"],
                "medium": s["by_severity"]["medium"],
                "low": s["by_severity"]["low"],
                "passed": s["passed"],
                "not_evaluable": s["not_evaluable"],
                "not_applicable": s["not_applicable"],
            },
            "top_risks": s["top_risks"],
            "source_diag": os.path.relpath(r["path"], os.path.dirname(os.path.abspath(__file__))),
        })

    # ---- 汇总：谁最差、哪条规则最常被触发 ----
    worst = max(companies, key=lambda c: c["overall_risk_score"]) if companies else None
    counter = {}
    for c in companies:
        for rid, cell in matrix[c["key"]].items():
            if cell["status"] == "triggered":
                counter.setdefault(rid, []).append(c["key"])
    rule_meta = {c["risk_id"]: c for c in rule_cols}
    hot = sorted(counter.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    most_triggered = [{
        "risk_id": rid,
        "risk_name": rule_meta.get(rid, {}).get("risk_name"),
        "category": rule_meta.get(rid, {}).get("category"),
        "companies": keys,
        "count": len(keys),
    } for rid, keys in hot[:10]]

    review = []
    for r in results:
        for q in r["res"]["review_queue"]:
            review.append(dict(q, company=company_key(r["diag"])))

    status_totals = {k: sum(1 for c in companies for cell in matrix[c["key"]].values()
                            if cell["status"] == k)
                     for k in ("triggered", "passed", "not_evaluable", "not_applicable")}

    # ---- 二维风险矩阵的坐标 ----
    # 年报记录的是已经发生的事，没有「未来发生概率」这种量。所以横轴不叫可能性，
    # 用「同类公司中已触发的比例」，可复算；纵轴用规则引擎的风险分。
    # 两轴都是查得到出处的数，不是估计值。
    rule_points = []
    for rc in rule_cols:
        rid = rc["risk_id"]
        trig = [k for k in matrix if (matrix[k].get(rid) or {}).get("status") == "triggered"]
        ev = [k for k in matrix
              if (matrix[k].get(rid) or {}).get("status") in ("triggered", "passed")]
        if not trig or not ev:
            continue                      # 没触发过的规则不落图：X=0 会挤成一堆看不清
        sc = [matrix[k][rid]["score"] for k in trig
              if matrix[k][rid].get("score") is not None]
        sev = collections.Counter(matrix[k][rid].get("severity") for k in trig
                                  if matrix[k][rid].get("severity"))
        rule_points.append({
            "risk_id": rid,
            "risk_name": rc["risk_name"],
            "category": rc["category"],
            "category_label": rc["category_label"],
            "breadth": round(100.0 * len(trig) / len(ev), 1),
            "intensity": round(sum(sc) / len(sc), 1) if sc else None,
            "n_triggered": len(trig),
            "n_evaluable": len(ev),
            "severity_mix": dict(sev),
            "companies": trig,
        })
    rule_points.sort(key=lambda p: (-(p["breadth"] or 0), -(p["intensity"] or 0), p["risk_id"]))

    # 象限分界取本批中位数，不用固定的 50% / 70 分。
    # 原因：一批公司里往往没有一条规则过半触发，画 50% 线会让全部点挤在左边，
    # 触发家数最多的规则反而落进「低频」区，读起来是错的。
    # 用中位数分界，象限表达的是「相对本批而言」，图上会写明分界值。
    def _median(vals):
        vals = sorted(v for v in vals if v is not None)
        if not vals:
            return None
        n = len(vals)
        return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 1)

    mid_x = _median([p["breadth"] for p in rule_points])
    mid_y = _median([p["intensity"] for p in rule_points])

    company_points = []
    for c in companies:
        cnt = c["counts"]
        ev = cnt["triggered"] + cnt["passed"]
        company_points.append({
            "key": c["key"],
            "name": c["name"],
            "ticker": c["ticker"],
            "breadth": round(100.0 * cnt["triggered"] / ev, 1) if ev else None,
            "score": c["overall_risk_score"],
            "risk_level": c["overall_risk_level"],
            "reliability": c["conclusion_reliability"],
            "n_triggered": cnt["triggered"],
            "n_not_evaluable": cnt["not_evaluable"],
            "n_evaluable": ev,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "generator": "risk-radar/scripts/build_risk_matrix.py",
        "rules_version": rules_doc.get("schema_version"),
        "industry_profile": {
            "profile_id": profile0.get("profile_id"),
            "label": profile0.get("label"),
            "statement_model": profile0.get("statement_model"),
            "benchmarks_calibrated": bool((profile0.get("benchmarks") or {}).get("calibrated")),
        },
        "comparability": {
            "same_industry": all((r["diag"].get("company") or {}).get("industry")
                                 for r in results),
            "industry_values": sorted({((r["diag"].get("company") or {}).get("industry") or "未识别")
                                       for r in results}),
            "profile_id": profile0.get("profile_id"),
            "periods": periods,
            "period_consistent": len(periods) == 1,
            "note": (
                "各公司行业字段齐全，按同行业口径横向比较。" if len(periods) == 1
                and all((r["diag"].get("company") or {}).get("industry") for r in results)
                else "行业字段缺失，矩阵只在同一行业剖面内可比，不能当作严格同行业对比；"
                     "跨行业排序仅供参考。" if not all((r["diag"].get("company") or {}).get("industry")
                                                for r in results)
                else "各公司报告期不同，趋势项（同比）的可比性下降，解读时需注意。"),
        },
        "companies": companies,
        "rules": rule_cols,
        "matrix": matrix,
        "risk_matrix_view": {
            "x_axis": {
                "label": "触发广度",
                "unit": "%",
                "desc": "该风险项在本批公司中被触发的比例（触发家数 / 可评估家数）。"
                        "衡量普遍性，不是未来发生概率的预测。",
            },
            "y_axis": {
                "label": "触发强度",
                "unit": "分",
                "desc": "触发该风险项的公司的平均风险分，由规则严重度决定（60 关注 / 85 重大）。",
            },
            "size_desc": "气泡大小 = 触发家数",
            "color_desc": "颜色 = 风险类别",
            "mid_x": mid_x if mid_x is not None else 50,
            "mid_y": mid_y if mid_y is not None else 70,
            "mid_basis": "本批中位数",
            "quadrants": [
                {"key": "q_tr", "label": "多家触发 · 强度偏高",
                 "desc": "相对本批，触发面更广且单项冲击更大，优先看"},
                {"key": "q_tl", "label": "少数触发 · 强度偏高",
                 "desc": "只有个别公司中招，但一旦中招冲击大，多为自身经营问题"},
                {"key": "q_br", "label": "多家触发 · 强度偏低",
                 "desc": "同行普遍都有的问题，单项冲击有限，属行业常态"},
                {"key": "q_bl", "label": "少数触发 · 强度偏低",
                 "desc": "相对少见且轻，可暂不处理"},
            ],
            "points": rule_points,
        },
        "company_view": {
            "x_axis": {"label": "触发规则占比", "unit": "%",
                       "desc": "该公司触发的规则数 / 可评估规则数"},
            "y_axis": {"label": "综合风险分", "unit": "分", "desc": "该公司加权综合风险分（0–100）"},
            "size_desc": "气泡大小 = 不可评估规则数（越大结论越不可靠）",
            "color_desc": "颜色 = 结论可信度",
            "points": company_points,
        },
        "summary": {
            "total_companies": len(companies),
            "total_rules": len(rule_cols),
            "status_totals": status_totals,
            "worst_company": ({"key": worst["key"], "name": worst["name"],
                               "overall_risk_level": worst["overall_risk_level"],
                               "overall_risk_score": worst["overall_risk_score"]} if worst else None),
            "avg_risk_score": round(sum(c["overall_risk_score"] for c in companies) / len(companies), 1)
            if companies else None,
            "most_triggered_rules": most_triggered,
        },
        "review_queue": review,
    }


# --------------------------------------------------------------------------- #
# 控制台输出
# --------------------------------------------------------------------------- #
STATUS_MARK = {"triggered": "!", "passed": "·", "not_evaluable": "?", "not_applicable": "—"}


def print_report(mx: dict) -> None:
    print()
    print(f"行业剖面：{mx['industry_profile']['profile_id']}（{mx['industry_profile']['label']}）")
    print(f"可比性：{mx['comparability']['note']}")
    print()
    header = (pad("公司", 26) + pad("期间", 7) + pad("综合", 14)
              + pad("触发", 6) + pad("重/关/提", 11) + pad("通过", 6)
              + pad("不可评估", 9) + pad("不适用", 7))
    print(header)
    print("-" * 96)
    for c in mx["companies"]:
        k = c["counts"]
        score = f"{c['overall_risk_level']} {c['overall_risk_score']}"
        sev = f"{k['high']}/{k['medium']}/{k['low']}"
        print(pad(c["name"] or c["key"], 26) + pad(c["period"] or "—", 7)
              + pad(score, 14) + pad(k["triggered"], 6) + pad(sev, 11)
              + pad(k["passed"], 6) + pad(k["not_evaluable"], 9) + pad(k["not_applicable"], 7))
    print()

    st = mx["summary"]["status_totals"]
    print(f"合计：触发 {st['triggered']} · 通过 {st['passed']} · 不可评估 {st['not_evaluable']} "
          f"· 不适用 {st['not_applicable']}　平均风险分 {mx['summary']['avg_risk_score']}")
    worst = mx["summary"]["worst_company"]
    if worst:
        print(f"风险最高：{worst['name']}（{worst['overall_risk_level']} {worst['overall_risk_score']}）")
    if mx["summary"]["most_triggered_rules"]:
        print()
        print("最常被触发的规则：")
        for h in mx["summary"]["most_triggered_rules"][:5]:
            print(f"  {h['risk_id']} {h['risk_name']}　{h['count']} 家：{'、'.join(h['companies'])}")
    pts = (mx.get("risk_matrix_view") or {}).get("points") or []
    if pts:
        t = pts[0]
        print()
        print(f"风险矩阵：{len(pts)} 条规则落图，最普遍的是 {t['risk_id']} {t['risk_name']}"
              f"（{t['n_triggered']}/{t['n_evaluable']} 家触发，广度 {t['breadth']}%）")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="多公司风险矩阵")
    ap.add_argument("--diag", nargs="+", help="多个 diagnosis 输出（compute_ratios 的 output_ratios.json）")
    ap.add_argument("--diag-dir", help="目录，读取其中全部 .json")
    ap.add_argument("--rules", default=DEFAULT_RULES)
    ap.add_argument("--industry", default=None, help="强制指定行业剖面（默认按各公司 industry 自动匹配）")
    ap.add_argument("--profile-dir", default=None)
    ap.add_argument("--comparison-dir", default=None,
                    help="同业对比目录（文件名与 ratios 同名），给了就用同业分位阈值")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    paths = collect_paths(args)
    with open(args.rules, encoding="utf-8") as f:
        rules_doc = json.load(f)

    mx = build(paths, rules_doc, args.industry, args.profile_dir, args.comparison_dir)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(mx, f, ensure_ascii=False,
                  indent=2 if args.pretty else None,
                  separators=None if args.pretty else (",", ":"))
        f.write("\n")

    print_report(mx)
    print(f"[OK] matrix -> {args.output}")


if __name__ == "__main__":
    main()
