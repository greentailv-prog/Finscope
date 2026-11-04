#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_peer_view.py
==================
同业对比可视化数据层：把篮子全体公司的指标 + 板块池分位数 + 杜邦三因子
汇成一份 peer_view.json，供 scripts_build_peer_view.py 渲染。

数据来源（出处可核对）
--------------------
- 每家公司指标值：cases/<篮子>/ratios/<code>.json（compute_ratios.py 产出，零猜测）
- 行业分位线：--board-pool 板块池（fetch_industry_samples.py 产出，含 n/status）
- 杜邦三因子：各公司 ratios 的 attribution.dupont.current（平均口径，
  三项相乘严格闭合到 ROE，闭合差一并透出）

口径说明（写在输出的 notes 里，页面同样显示）
------------------------------------------
- dso/dio：篮子 ratios 里是周转次数（次/年），板块池是天数口径。
  换算 365/次数，公式标注，不算猜数。
- 板块池指标单位与 ratios 归一一致（比率是小数），无需换算。

用法
----
    python3 risk-radar/scripts/build_peer_view.py \
        --ratios-dir cases/a-share-basket/ratios \
        --board-pool risk-radar/data/peer_samples/boards/BK1277.json \
        --target 600519 \
        -o cases/a-share-basket/peer_view.json --pretty
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from datetime import datetime, timezone, timedelta

CN_TZ = timezone(timedelta(hours=8))

# 可视化指标集：basket_key -> 板块池 key 的映射 + 展示元数据
INDICATORS = [
    # (metric, 展示名, 单位, 方向, 换算说明)
    ("roe", "ROE（归母，加权）", "ratio", "higher_better", None),
    ("gross_margin", "毛利率", "ratio", "higher_better", None),
    ("net_margin", "净利率", "ratio", "higher_better", "篮子为全口径净利率；板块池 XSJLL 同口径"),
    ("debt_to_assets", "资产负债率", "ratio", "lower_better", None),
    ("current_ratio", "流动比率", "ratio", "higher_better", None),
    ("quick_ratio", "速动比率", "ratio", "higher_better", None),
    ("dso", "应收账款周转天数", "days", "lower_better", "365 / 应收周转次数"),
    ("dio", "存货周转天数", "days", "lower_better", "365 / 存货周转次数"),
]

DUPONT_FACTORS = [
    ("net_margin", "净利率", "ratio"),
    ("asset_turnover", "总资产周转率", "ratio"),
    ("equity_multiplier", "权益乘数", "multiplier"),
]


def short_name(full: str) -> str:
    """贵州茅台酒股份有限公司 -> 贵州茅台；截断过长的全称便于落图。"""
    s = re.sub(r"(股份有限公司|有限责任公司|集团股份有限公司)$", "", full or "")
    return s or (full or "")


def _find_metric(ratios: dict, key: str):
    """ratios 是类别嵌套结构，扁平查找第一处同名指标。"""
    for _cat, items in (ratios or {}).items():
        if isinstance(items, dict) and key in items:
            return items[key]
    return None


def _value_of(spec: dict):
    v = (spec or {}).get("value")
    return v if isinstance(v, (int, float)) else None


def load_company(path: str) -> dict:
    d = json.load(open(path, "r", encoding="utf-8"))
    comp = d.get("company") or {}
    return {
        "path": path,
        "code": str(comp.get("ticker_code") or comp.get("ticker") or ""),
        "name": short_name(comp.get("name") or ""),
        "industry": comp.get("industry"),
        "ratios": d.get("ratios") or {},
        "dupont": (d.get("attribution") or {}).get("dupont") or {},
    }


def main():
    ap = argparse.ArgumentParser(description="同业对比可视化数据层")
    ap.add_argument("--ratios-dir", required=True, help="篮子 ratios 目录（每家一个 json）")
    ap.add_argument("--board-pool", default=None, help="板块池 JSON（fetch_industry_samples.py 产出）")
    ap.add_argument("--target", required=True, help="目标公司 6 位代码")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.ratios_dir, "*.json")))
    if not files:
        raise SystemExit("[ERR] %s 下没有 ratios JSON" % args.ratios_dir)
    companies = [load_company(f) for f in files]
    by_code = {c["code"]: c for c in companies}
    target = by_code.get(args.target)
    if not target:
        raise SystemExit("[ERR] 目标公司 %s 不在篮子里：%s"
                         % (args.target, "、".join(sorted(by_code))))

    pool = json.load(open(args.board_pool, "r", encoding="utf-8")) if args.board_pool else None
    pool_metrics = (pool or {}).get("metrics") or {}
    notes = []

    indicators = []
    for metric, label, unit, direction, conv in INDICATORS:
        spec_pool = pool_metrics.get(metric) or {}
        rows, missing = [], []
        for c in companies:
            if metric == "dso":
                spec = _find_metric(c["ratios"], "ar_turnover")
                v = _value_of(spec)
                v = round(365.0 / v, 2) if v else None       # 次 -> 天
            elif metric == "dio":
                spec = _find_metric(c["ratios"], "inventory_turnover")
                v = _value_of(spec)
                v = round(365.0 / v, 2) if v else None
            else:
                spec = _find_metric(c["ratios"], metric)
                v = _value_of(spec)
            row = {"code": c["code"], "name": c["name"], "value": v}
            if v is None:
                st = (spec or {}).get("status") or "not_evaluable"
                row["missing_reason"] = st
                missing.append(c["name"])
            rows.append(row)
        if missing:
            notes.append("%s：缺 %s（%s）" % (label, "、".join(missing),
                                          "；".join(set(m["missing_reason"] for m in rows if m["value"] is None))))
        indicators.append({
            "metric": metric,
            "label": label,
            "unit": unit,
            "direction": direction,
            "convert_note": conv,
            "companies": rows,
            "target_value": _value_of(_find_metric(target["ratios"], metric)) if metric not in ("dso", "dio")
                            else next((r["value"] for r in rows if r["code"] == target["code"]), None),
            "pool": {
                "median": spec_pool.get("median"),
                "p25": spec_pool.get("p25"),
                "p75": spec_pool.get("p75"),
                "n": spec_pool.get("n"),
                "status": spec_pool.get("status"),
            } if spec_pool else None,
        })

    # ---- 杜邦三因子跨公司对比 ---- #
    dupont = []
    for c in companies:
        cur = (c["dupont"] or {}).get("current") or {}
        nm, tat, em = cur.get("net_margin"), cur.get("asset_turnover"), cur.get("equity_multiplier")
        row = {"code": c["code"], "name": c["name"]}
        if None not in (nm, tat, em):
            row.update({"net_margin": nm, "asset_turnover": tat,
                        "equity_multiplier": em, "roe": cur.get("roe")})
            # 闭合差：三因子乘积应严格等于 ROE（compute_ratios 的口径保证），透出以供核对
            prod = nm * tat * em
            row["closure_delta"] = round(prod - (cur.get("roe") or 0), 6)
        else:
            # 杜邦缺因子时如实标注原因（通常 ROE 本身 not_meaningful）
            roe_spec = _find_metric(c["ratios"], "roe") or {}
            row["missing_reason"] = roe_spec.get("status") or "not_evaluable"
            notes.append("杜邦三因子：%s 缺（%s）" % (c["name"], row["missing_reason"]))
        dupont.append(row)

    out = {
        "schema": "finradar.peer_view/1.0",
        "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "target": {"code": target["code"], "name": target["name"]},
        "board": {"code": (pool or {}).get("board_code"), "name": (pool or {}).get("board_name"),
                  "as_of": (pool or {}).get("as_of"),
                  "source": (pool or {}).get("source")} if pool else None,
        "companies": [{"code": c["code"], "name": c["name"]} for c in companies],
        "indicators": indicators,
        "dupont": dupont,
        "dupont_factors": [{"key": k, "label": l, "unit": u} for k, l, u in DUPONT_FACTORS],
        "notes": notes,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2 if args.pretty else None)
        f.write("\n")
    print("[OK] peer_view -> %s" % args.output)
    print("     公司 %d 家 | 指标 %d 项 | 杜邦可比 %d 家 | 板块池 %s"
          % (len(companies), len(indicators),
             sum(1 for r in dupont if "roe" in r),
             "%s %s" % ((pool or {}).get("board_code"), (pool or {}).get("board_name")) if pool else "未提供"))
    for n in notes:
        print("     note:", n)


if __name__ == "__main__":
    main()
