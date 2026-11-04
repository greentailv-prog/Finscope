#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_industry_samples.py —— 任意行业的同业基准样本池（板块级）。

解决什么问题
------------
银行业此前有专属的 fetch_bank_samples.py；其他行业（白酒、电池、机械……）没有
同业分位可用。本脚本把建池能力通用化：给一个东方财富行业板块，抓成分股当期
年报的关键指标，算分位数，产出 `peer_samples/boards/<BKxxxx>.json`。

detect_risks.py 用 `--benchmarks` 读这个文件后，任何行业的 P06（毛利率 vs 中位数）、
S01（资产负债率 vs P75）等同业阈值规则即自动生效——**不需要为每个行业写代码**。

三种指定板块的方式
------------------
    --board BK0477          板块代码
    --board 白酒            板块名称（模糊匹配，命中"白酒Ⅱ"）
    --code 600519           公司代码，自动解析其所属行业板块

指标与单位（2026-11-05 用茅台年报复核过）
----------------------------------------
    roe              ROEJQ/100        加权净资产收益率（%→ratio）
    gross_margin     XSMLL/100        毛利率
    net_margin       XSJLL/100        销售净利率
    debt_to_assets   ZCFZL/100        资产负债率
    current_ratio    LD               流动比率（接口直接给倍数，不再除 100）
    quick_ratio      SD               速动比率（同上）
    dso              YSZKZZTS         应收账款周转天数（天）
    dio              CHZZTS           存货周转天数（天）

用法
----
    python3 fetch_industry_samples.py --board 白酒                # 预演
    python3 fetch_industry_samples.py --board 白酒 --write        # 落盘
    python3 fetch_industry_samples.py --code 600519 --write
    python3 fetch_industry_samples.py --code 601398 --write       # 银行板块也能用

抓完后：detect_risks.py --benchmarks risk-radar/data/peer_samples/boards/BKxxxx.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "data", "peer_samples", "boards")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
QUOTE_URL = "https://push2.eastmoney.com/api/qt"
MAIN_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# 指标 → (东财字段, 换算函数, 单位)。换算已在 2026-11-05 用茅台 2025 年报复核。
METRICS = {
    "roe": ("ROEJQ", lambda v: v / 100.0, "ratio"),
    "gross_margin": ("XSMLL", lambda v: v / 100.0, "ratio"),
    "net_margin": ("XSJLL", lambda v: v / 100.0, "ratio"),
    "debt_to_assets": ("ZCFZL", lambda v: v / 100.0, "ratio"),
    "current_ratio": ("LD", lambda v: v, "ratio"),
    "quick_ratio": ("SD", lambda v: v, "ratio"),
    "dso": ("YSZKZZTS", lambda v: v, "days"),
    "dio": ("CHZZTS", lambda v: v, "days"),
}

MIN_CALIBRATED_N = 15   # 与 calibrate.py 同一分档
MIN_INDICATIVE_N = 5
QUANTILES = (("p10", 0.10), ("p25", 0.25), ("median", 0.50),
             ("p75", 0.75), ("p90", 0.90))


# --------------------------------------------------------------------------- #
# 请求
# --------------------------------------------------------------------------- #
def _get(url: str, params: dict, retries: int = 3):
    q = urllib.parse.urlencode(params, safe="()")
    req = urllib.request.Request(url + "?" + q,
                                 headers={"User-Agent": UA,
                                          "Referer": "https://quote.eastmoney.com/"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(0.8 * (i + 1))
    raise RuntimeError("接口请求失败：%s" % last)


def list_boards() -> list:
    """全部东财板块（含行业与细分，共 ~500 个）[(code, name)]。

    接口按代码降序，必须升序翻页才能拿全 BK04xx 段（银行Ⅱ、酿酒行业等）。
    """
    rows = []
    for pn in range(1, 8):
        d = _get(QUOTE_URL + "/clist/get", {
            "pn": str(pn), "pz": "100", "po": "0", "np": "1", "fltt": "2",
            "invt": "2", "fid": "f12", "fs": "m:90+t:2", "fields": "f12,f14"})
        data = (d.get("data") or {}).get("diff") or []
        rows += data
        if len(data) < 100:
            break
    return [(x["f12"], x["f14"]) for x in rows]


def resolve_board(board: str | None, code: str | None) -> tuple[str, str]:
    """返回 (板块代码, 板块名称)。"""
    if code:
        secid = ("1." if re.match(r"^6", code) else "0.") + code
        d = _get(QUOTE_URL + "/stock/get", {
            "secid": secid, "invt": "2", "fltt": "2", "fields": "f12,f14,f127"})
        name = (d.get("data") or {}).get("f127")
        if not name:
            raise SystemExit("[ERR] %s 查不到所属行业板块（f127）" % code)
        board = name
    if not board:
        raise SystemExit("[ERR] 需要 --board 或 --code")
    boards = list_boards()
    if board.upper().startswith("BK"):
        for c, n in boards:
            if c == board.upper():
                return c, n
        raise SystemExit("[ERR] 找不到板块代码 %s" % board)
    hit = [(c, n) for c, n in boards if board in n]
    if not hit:
        raise SystemExit("[ERR] 名称含 '%s' 的板块不存在，示例：%s"
                         % (board, "、".join(n for _, n in boards[:10])))
    if len(hit) > 1:
        print("[提示] 名称模糊命中多个板块：", "、".join("%s(%s)" % (c, n) for c, n in hit))
        c, n = hit[0]
        print("       取第一个：%s %s" % (c, n))
    return hit[0]


def board_members(bk: str, cap: int) -> list:
    d = _get(QUOTE_URL + "/clist/get", {
        "pn": "1", "pz": str(cap), "po": "1", "np": "1", "fltt": "2", "invt": "2",
        "fid": "f20", "fs": "b:%s" % bk, "fields": "f12,f14"})   # 按总市值排序取头部
    rows = (d.get("data") or {}).get("diff") or []
    return [(x["f12"], x["f14"]) for x in rows]


def company_metrics(code: str, year: int) -> dict:
    """单家公司当期年报指标（已换算单位）。缺的字段不猜数。"""
    q = urllib.parse.urlencode({
        "reportName": "RPT_F10_FINANCE_MAINFINADATA", "columns": "ALL",
        "filter": '(SECURITY_CODE="%s")(REPORT_DATE_NAME="%d年报")' % (code, year),
        "pageNumber": "1", "pageSize": "1",
        "sortColumns": "REPORT_DATE", "sortTypes": "-1"}, safe="()")
    req = urllib.request.Request(MAIN_URL + "?" + q,
                                 headers={"User-Agent": UA,
                                          "Referer": "https://emweb.securities.eastmoney.com/"})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    data = ((d.get("result") or {}).get("data")) or []
    if not data:
        return {}
    rec = data[0]
    out = {}
    for mkey, (field, conv, _unit) in METRICS.items():
        v = rec.get(field)
        if isinstance(v, (int, float)):
            try:
                out[mkey] = conv(v)
            except Exception:
                pass
    return out


# --------------------------------------------------------------------------- #
# 统计（与 calibrate.py 同一实现）
# --------------------------------------------------------------------------- #
def percentile(sorted_vals: list, q: float):
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    pos = (n - 1) * q
    lo, hi = int(pos // 1), int(-(-pos // 1))
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


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="抓任意行业板块的同业基准样本池")
    ap.add_argument("--board", help="板块代码（BK0477）或名称（白酒）")
    ap.add_argument("--code", help="公司代码，自动解析其所属行业板块")
    ap.add_argument("--year", type=int, default=_dt.date.today().year - 1,
                    help="年报期间（默认上一年度）")
    ap.add_argument("--cap", type=int, default=40,
                    help="按市值取成分股上限（默认 40，够 n≥15 的 calibrated 档）")
    ap.add_argument("--write", action="store_true", help="写入 peer_samples/boards/；不给则只预演")
    args = ap.parse_args()

    bk, bkname = resolve_board(args.board, args.code)
    members = board_members(bk, args.cap)
    print("板块 %s %s · 成分股取前 %d 家（按总市值）· %d 年报" % (bk, bkname, len(members), args.year))

    per_metric = {m: [] for m in METRICS}
    missing_cnt = {m: 0 for m in METRICS}
    for i, (code, name) in enumerate(members, 1):
        vals = company_metrics(code, args.year)
        time.sleep(0.25)
        got = " ".join("%s=%.4g" % (k, v) for k, v in sorted(vals.items())) or "（全部缺失）"
        print("  [%2d/%d] %s %s  %s" % (i, len(members), code, name, got))
        for m in METRICS:
            v = vals.get(m)
            if v is None:
                missing_cnt[m] += 1
            else:
                per_metric[m].append({"company": name, "code": code, "value": round(float(v), 8)})

    metrics_out = {}
    print("\n分位数汇总：")
    for m, raw in per_metric.items():
        vals = sorted(x["value"] for x in raw)
        n = len(vals)
        unit = METRICS[m][2]
        spec = {"unit": unit, "n": n, "status": status_of(n),
                "source": "东方财富 F10 %s · %s 板块 %d 家，%d 年报" % (METRICS[m][0], bkname, n, args.year),
                "as_of": "%d-12-31" % args.year}
        if n:
            spec.update({k: round(percentile(vals, q), 8) for k, q in QUANTILES})
            print("  %-16s n=%2d  %-11s %s" % (m, n, spec["status"],
                  "  ".join("%s=%s" % (k, ("%.1f天" % v) if unit == "days" else "%.2f%%" % (v * 100))
                            for k, v in spec.items() if k in dict(QUANTILES))))
        else:
            print("  %-16s n=0   missing" % m)
        metrics_out[m] = spec

    out = {
        "schema_version": "finradar.board-pool/1.0",
        "board_code": bk,
        "board_name": bkname,
        "industry": bkname,
        "as_of": "%d-12-31" % args.year,
        "sample_definition": "东方财富行业板块 %s（%s）按市值前 %d 家，%d 年报披露值，"
                             "scripts/fetch_industry_samples.py 生成" % (bk, bkname, len(members), args.year),
        "owner": "B",
        "note": "板块级同业基准池。detect_risks.py --benchmarks 本文件后，benchmark_judge "
                "规则自动改用本板块分位数判定；n<5 的指标不参与判定（如实标 missing）。",
        "metrics": metrics_out,
    }

    out_path = os.path.join(OUT_DIR, "%s.json" % bk)
    usable = [m for m, s in metrics_out.items() if s["n"] >= MIN_INDICATIVE_N]
    print("\n可用指标（n≥5）：%s" % ("、".join(usable) or "无"))

    if args.write:
        if not usable:
            print("[拒绝写盘] 没有任何指标达到 n≥5，写进去也不会生效。先扩 --cap 或查接口。")
            return 1
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("[OK] 已写入 %s" % out_path)
        print("用法示例：python3 detect_risks.py --ratios ... --rules ... "
              "--benchmarks %s -o ..." % out_path)
    else:
        print("（预演模式，未写盘。确认无误后加 --write）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
