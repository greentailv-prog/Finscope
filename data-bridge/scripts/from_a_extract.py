#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A 的抽取结果 → B 的输入 JSON。

A 的输出是「一条科目一条记录 + series{年份: 值}」，B 要的是
「科目 → {年份 → {值, 单位, 出处, 页码}}」。本脚本只做结构转换与字段改名，
**不重算、不补数、不改单位**：A 说 found 就 found，A 缺就是缺。

两种来源都认：
  - 旧键：cash / equity_attr / net_profit_attr / cfo / cfi / cff / operating_cost
  - canonical 键：current_assets / current_liabilities / net_income_excl_nonrecurring / rnd_expense

用法：
    python3 from_a_extract.py --a <A输出.json> --out <B输入.json>
    python3 from_a_extract.py --dir <A输出目录> --out-dir <B输入目录>
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import field_map as FM  # noqa: E402


def _years(rec: dict):
    s = rec.get("series") or {}
    out = {str(y): v for y, v in s.items() if v is not None}
    if not out and rec.get("status") == "found" and rec.get("value") is not None:
        y = str(rec.get("period") or "")[:4]
        if y:
            out[y] = rec["value"]
    return out


def convert(a_obj: dict) -> dict:
    fin = a_obj.get("financials") or {}
    company = a_obj.get("company") or {}

    years = set()
    for rec in fin.values():
        years.update(_years(rec))
    periods = sorted(years)

    financials = {}
    for a_key, rec in fin.items():
        b_key = FM.b_key(a_key)
        if b_key not in FM.B_FIELDS:
            continue  # 不认识就不搬，避免脏字段进引擎
        series = _years(rec)
        if not series:
            continue
        cells = {}
        for y, v in series.items():
            cell = {
                "value": float(v),
                "unit": rec.get("unit") or "元",
                "unit_raw": rec.get("unit_raw") or rec.get("unit") or "元",
                "status": "found" if rec.get("status") == "found" else (rec.get("status") or "found"),
                "source_type": "pdf",
                "source": rec.get("source"),
                "page": rec.get("page"),
                "pdf_page": rec.get("pdf_page") or rec.get("page"),
                "raw_text": rec.get("raw_text"),
                "basis": rec.get("basis"),
            }
            # A 抽取时对可疑值做过的补救必须带到 B，否则 B 会把推算值当披露值：
            #   status_note   —— A 的处理说明，如「报告权益低于归母权益，按…倒算」
            #   value_original—— A 改写前的原值（倒算时才写）
            #   confidence    —— A 的置信度（倒算条目 0.7，正常 0.95）
            # derived 是判定结果：值不是从报表行直接抄的，勾稽/对比都要绕开。
            note = rec.get("status_note") or ""
            raw = rec.get("raw_text") or ""
            if note or rec.get("value_original") is not None:
                cell["status_note"] = note or None
                if rec.get("value_original") is not None:
                    cell["value_original"] = rec["value_original"]
                if rec.get("confidence") is not None:
                    cell["confidence"] = rec["confidence"]
                if "倒算" in note or "倒算" in raw or rec.get("value_original") is not None:
                    cell["derived"] = True
            cells[y] = cell
        financials[b_key] = dict(sorted(cells.items()))
    if not financials:
        raise ValueError("没有可转换的科目：A 的键一个都没匹配上")

    missing = [f for f in FM.B_FIELDS if f not in financials]

    return {
        "schema_version": "finradar.extraction/2.0",
        "meta": {
            "periods": periods,
            "default_unit": "元",
            "currency": "CNY",
            "source_mode": "upload",
            "data_source": "annual_report_pdf",
            "amount_unit": "元",
            "consolidated": True,
            "industry": company.get("industry") or None,
            "note": "上传模式：每个科目带印刷页码与 PDF 物理页",
            # A 抽的是资产负债表「货币资金」，与现金流量表「现金及现金等价物」
            # 不同源，现金净变动勾稽在口径上不成立——声明清楚，不假装查过。
            "alignment_flags": {"cash_bridge": "not_comparable"},
        },
        "company": {
            "name": company.get("name"),
            "ticker": company.get("ticker"),
            "industry": company.get("industry") or None,
            "report_period": company.get("report_period") or (periods[-1] if periods else None),
            "report_title": company.get("report_title"),
        },
        "financials": financials,
        "sources": a_obj.get("sources") or [],
        "extraction_meta": {
            "converter": "data-bridge/from_a_extract.py",
            "periods": periods,
            "given_count": len(financials),
            "missing_fields": missing,
            "a_schema_version": a_obj.get("schema_version"),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="A 抽取结果 → B 输入")
    ap.add_argument("--a", help="单个 A 输出 JSON")
    ap.add_argument("--dir", help="A 输出目录（批量）")
    ap.add_argument("--out", help="单文件输出路径")
    ap.add_argument("--out-dir", help="批量输出目录")
    args = ap.parse_args()

    files = []
    if args.a:
        files = [args.a]
    elif args.dir:
        files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    else:
        ap.error("需要 --a 或 --dir")

    for p in files:
        try:
            with open(p, encoding="utf-8") as f:
                a_obj = json.load(f)
            obj = convert(a_obj)
        except Exception as e:
            print("[FAIL] %s -> %s" % (os.path.basename(p), e), file=sys.stderr)
            continue
        if len(files) == 1 and args.out:
            out = args.out
        else:
            base = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
            os.makedirs(base, exist_ok=True)
            ticker = (obj["company"].get("ticker") or os.path.splitext(os.path.basename(p))[0])
            out = os.path.join(base, "input_%s.json" % ticker.replace(".", "_"))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        print("[OK] %-28s %-8s 期间 %s 科目 %2d 缺 %2d -> %s" % (
            os.path.basename(p)[:28], (obj["company"].get("name") or "")[:8],
            "-".join(obj["meta"]["periods"]), obj["extraction_meta"]["given_count"],
            len(obj["extraction_meta"]["missing_fields"]), out))


if __name__ == "__main__":
    main()
