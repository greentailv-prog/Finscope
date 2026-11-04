#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_bank_samples.py —— 刷新银行业风险阈值的校准样本池。

抓什么
------
东方财富公开接口，20 家上市银行的：
- 净息差 NIM            → F10 主要指标 NET_INTEREST_MARGIN（%）
- 成本收入比            → F10 利润表自算：业务及管理费(MANAGE_EXPENSE) / 营业收入(TOTAL_OPERATE_INCOME)
口径已与 B 指标引擎对齐（2026-11-04 用工行年报复算，1.28% / 28.05% 完全一致）。

为什么只抓这两项
----------------
B01-B05 / B11 属 regulatory 或 self_delta 阈值：前者用法规硬线
（见行业剖面 regulatory_basis），后者是公司自比，都不需要同业分位数。
真正需要 peer_percentile 的只有 NIM（B06，行业中位数）与成本收入比（B07，行业 P75）。

样本名单（n=20，写死以保证可复现）
----------------------------------
国有六大行 6 家 + 股份制商业银行 9 家 + 头部城商行 5 家。
扩样本时改 BANKS 表即可，分位数由 calibrate.py 重算。

用法
----
    python3 fetch_bank_samples.py                 # 预演：抓数、算分位、不落盘
    python3 fetch_bank_samples.py --write         # 写入 data/peer_samples/banking.json
    python3 fetch_bank_samples.py --year 2025     # 指定年报期间（默认上一年度）

抓完后执行：
    python3 calibrate.py --industry banking --write
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(BASE, "data", "peer_samples", "banking.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MAIN_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
INC_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"

# 20 家样本：国有六大行 6 + 股份制 9 + 头部城商行 5
BANKS = [
    ("601398", "工商银行"), ("601939", "建设银行"), ("601288", "农业银行"),
    ("601988", "中国银行"), ("601328", "交通银行"), ("601658", "邮储银行"),
    ("600036", "招商银行"), ("601166", "兴业银行"), ("601998", "中信银行"),
    ("600000", "浦发银行"), ("600016", "民生银行"), ("601818", "光大银行"),
    ("000001", "平安银行"), ("600015", "华夏银行"), ("601916", "浙商银行"),
    ("601169", "北京银行"), ("600919", "江苏银行"), ("002142", "宁波银行"),
    ("601229", "上海银行"), ("601009", "南京银行"),
]


def _get(url: str, params: dict, retries: int = 3):
    q = urllib.parse.urlencode(params, safe="()")
    req = urllib.request.Request(url + "?" + q,
                                 headers={"User-Agent": UA,
                                          "Referer": "https://emweb.securities.eastmoney.com/"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(0.8 * (i + 1))
    raise RuntimeError("接口请求失败：%s" % last)


def fetch_nim(code: str, year: int):
    """净息差（%），取不到返回 None。"""
    d = _get(MAIN_URL, {
        "reportName": "RPT_F10_FINANCE_MAINFINADATA", "columns": "ALL",
        "filter": '(SECURITY_CODE="%s")(REPORT_DATE_NAME="%d年报")' % (code, year),
        "pageNumber": "1", "pageSize": "1",
        "sortColumns": "REPORT_DATE", "sortTypes": "-1"})
    data = ((d.get("result") or {}).get("data")) or []
    if not data:
        return None
    v = data[0].get("NET_INTEREST_MARGIN")
    return float(v) if isinstance(v, (int, float)) else None


def fetch_cost_to_income(code: str, year: int):
    """成本收入比 = 业务及管理费 / 营业收入。任一项缺失返回 None，不猜数。"""
    d = _get(INC_URL, {
        "reportName": "RPT_F10_FINANCE_GINCOME", "columns": "ALL",
        "filter": '(SECUCODE="%s.SH")(REPORT_TYPE="年报")' % code,
        "pageNumber": "1", "pageSize": "10",
        "sortColumns": "REPORT_DATE", "sortTypes": "-1"})
    data = ((d.get("result") or {}).get("data")) or []
    rec = next((r for r in data
                if str(r.get("REPORT_DATE") or "").startswith("%d-12-31" % year)), None)
    if rec is None:
        return None
    exp = rec.get("MANAGE_EXPENSE")
    inc = rec.get("TOTAL_OPERATE_INCOME")
    if not isinstance(exp, (int, float)) or not isinstance(inc, (int, float)) or inc == 0:
        return None
    return exp / inc * 100.0     # 与 NET_INTEREST_MARGIN 同为百分数口径


def collect(year: int):
    nim_vals, cti_vals, missing = [], [], []
    for code, name in BANKS:
        nim = fetch_nim(code, year)
        time.sleep(0.3)
        cti = fetch_cost_to_income(code, year)
        time.sleep(0.3)
        if nim is None:
            nim_vals.append({"company": name, "code": code, "value": None})
            missing.append("%s NIM" % name)
        else:
            nim_vals.append({"company": name, "code": code, "value": round(nim / 100.0, 6)})
        if cti is None:
            cti_vals.append({"company": name, "code": code, "value": None})
            missing.append("%s 成本收入比" % name)
        else:
            cti_vals.append({"company": name, "code": code, "value": round(cti / 100.0, 6)})
        print("  %-8s %s  NIM=%s  成本收入比=%s" % (
            code, name,
            "—" if nim is None else "%.2f%%" % nim,
            "—" if cti is None else "%.2f%%" % cti))
    return nim_vals, cti_vals, missing


def main():
    ap = argparse.ArgumentParser(description="抓取银行业阈值校准样本（NIM / 成本收入比）")
    ap.add_argument("--year", type=int, default=_dt.date.today().year - 1,
                    help="年报期间（默认上一年度）")
    ap.add_argument("--write", action="store_true", help="写入 peer_samples/banking.json；不给则只预演")
    args = ap.parse_args()

    year = args.year
    print("抓取 %d 年报 · 20 家上市银行" % year)
    nim_vals, cti_vals, missing = collect(year)

    n_nim = sum(1 for x in nim_vals if x["value"] is not None)
    n_cti = sum(1 for x in cti_vals if x["value"] is not None)
    print("\n有效样本：NIM %d/20，成本收入比 %d/20" % (n_nim, n_cti))
    if missing:
        print("缺失（不猜数，原样记 null）：", "、".join(missing))

    src = ("东方财富 F10：主要指标 NET_INTEREST_MARGIN；利润表自算 "
           "业务及管理费/营业收入（2026-11-04 用工行年报复算口径一致）")

    with open(OUT_PATH, encoding="utf-8") as f:
        pool = json.load(f)

    pool["as_of"] = "%d-12-31" % year
    pool["sample_definition"] = (
        "20 家上市银行（国有六大行 6 + 股份制 9 + 头部城商行 5，名单见 metrics 各项 values），"
        "取 %d 年报披露值；由 scripts/fetch_bank_samples.py 刷新" % year)
    pool.setdefault("metrics", {})
    pool["metrics"]["nim"] = {
        "unit": "ratio", "values": nim_vals, "source": src, "as_of": "%d-12-31" % year}
    pool["metrics"]["cost_to_income"] = {
        "unit": "ratio", "values": cti_vals, "source": src, "as_of": "%d-12-31" % year}
    # npl_ratio / provision_coverage / capital_adequacy_ratio 属 regulatory 阈值，
    # 判定走法规硬线（行业剖面 regulatory_basis），不参与分位数校准
    pool["pending_metrics"] = {
        "npl_ratio": {
            "type": "regulatory",
            "why": "阈值是监管红线（B02：150%，可差异化下调至 120%–150%），分位数不参与判定；"
                   "同业分位仅作参考，如需展示可另抓",
            "where": "金融监管总局「商业银行主要监管指标」季度表，或各行年报"},
        "provision_coverage": {
            "type": "regulatory",
            "why": "同上，B02 判定用法规硬线，不用同业分位",
            "where": "同上"},
        "capital_adequacy_ratio": {
            "type": "regulatory",
            "why": "B04/B05 用《商业银行资本管理办法》底线（8%/8.25% 等），分位数不参与判定",
            "where": "同上"},
    }

    summary = json.dumps({k: v for k, v in pool["metrics"].items()
                          if k in ("nim", "cost_to_income")}, ensure_ascii=False)[:200]
    print("\n样本池更新预览：", summary, "...")

    if args.write:
        if n_nim < 5 or n_cti < 5:
            print("[拒绝写盘] 有效样本 <5 家，写进去也只会标 missing。先排查接口或扩样本。")
            return 1
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(pool, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("[OK] 已写入 %s" % OUT_PATH)
        print("下一步：python3 calibrate.py --industry banking --write")
    else:
        print("（预演模式，未写盘。确认无误后加 --write）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
