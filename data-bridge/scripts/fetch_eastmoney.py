#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入股票代码，从东方财富公开接口抓三年年报数据，直接产出 B 的输入 JSON。

零第三方依赖，只用标准库。设计上的三条约束：

1. **离线缓存**：同一代码 7 天内不重复请求，避免反复抓同一份数据。
2. **在线模式没有页码**：`source_type="online"`，只写数据源、字段名、链接。
   绝不把接口数据标成年报页码——那是伪造出处。
3. **不猜数**：接口没给的科目，`value=null` + `status="not_found"`，不写 0。

用法：
    python3 fetch_eastmoney.py --code 600519
    python3 fetch_eastmoney.py --code 600519 --years 3 --out input_600519.json
    python3 fetch_eastmoney.py --codes 600519,000858,000333 --out-dir ./inputs
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import field_map as FM  # noqa: E402

F10_HOST = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
CPD_HOST = "https://datacenter-web.eastmoney.com/api/data/v1/get"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
CACHE_DAYS = 7


# --------------------------------------------------------------------------- #
# 基础请求
# --------------------------------------------------------------------------- #
def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, name)


def _cache_get(name: str):
    p = _cache_path(name)
    if not os.path.exists(p):
        return None
    age = time.time() - os.path.getmtime(p)
    if age > CACHE_DAYS * 86400:
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_put(name: str, obj) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _get(url: str, params: dict, retries: int = 3):
    # 只保留括号不转义：接口要求 filter 里的 = 与引号都必须是 %3D / %22
    q = urllib.parse.urlencode(params, safe="()")
    req = urllib.request.Request(url + "?" + q, headers={"User-Agent": UA,
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


def to_secucode(code: str) -> str:
    """6 位代码 → 带交易所后缀。4/8 开头是北交所。"""
    code = str(code).strip()
    if "." in code:
        return code.upper()
    if len(code) != 6 or not code.isdigit():
        raise ValueError("股票代码应为 6 位数字，例如 600519")
    if code[0] == "6":
        return code + ".SH"
    if code[0] in "03":
        return code + ".SZ"
    if code[0] in "48":
        return code + ".BJ"
    raise ValueError("无法判断交易所：%s" % code)


# --------------------------------------------------------------------------- #
# 取数
# --------------------------------------------------------------------------- #
def fetch_statements(secucode: str, years: int, refresh: bool = False) -> dict:
    """取三张表的年报数据，返回 {report: [行, ...]}，按年份降序。"""
    out = {}
    for key, report_name in FM.EM_REPORTS.items():
        name = "stmt_%s_%s_%s.json" % (secucode.replace(".", "_"), key, years)
        if not refresh:
            hit = _cache_get(name)
            if hit is not None:
                out[key] = hit
                continue
        payload = _get(F10_HOST, {
            "reportName": report_name,
            "columns": "ALL",
            "filter": '(SECUCODE="%s")(REPORT_TYPE="年报")' % secucode,
            "pageSize": years,
            "pageNumber": 1,
            "sortColumns": "REPORT_DATE",
            "sortTypes": -1,
            "source": "HSF10",
            "client": "PC",
        })
        rows = ((payload.get("result") or {}).get("data") or [])
        out[key] = rows
        _cache_put(name, rows)
        time.sleep(0.25)
    return out


def fetch_profile(code6: str, refresh: bool = False):
    """取公司简称与所属板块，用于 company 与行业剖面匹配。"""
    name = "profile_%s.json" % code6
    if not refresh:
        hit = _cache_get(name)
        if hit is not None:
            return hit
    payload = _get(CPD_HOST, {
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,TRADE_MARKET",
        "filter": '(SECURITY_CODE="%s")' % code6,
        "pageSize": 1,
        "pageNumber": 1,
    })
    rows = ((payload.get("result") or {}).get("data") or [])
    prof = rows[0] if rows else {}
    _cache_put(name, prof)
    return prof


def _year_of(row) -> str:
    d = str(row.get("REPORT_DATE") or "")
    return d[:4] if len(d) >= 4 else ""


def _pick(row: dict, candidates):
    """按候选字段顺序取第一个非空值。"""
    for c in candidates:
        v = row.get(c)
        if v is not None:
            return v, c
    return None, None


def build_b_input(code: str, years: int = 3, refresh: bool = False) -> dict:
    secucode = to_secucode(code)
    code6 = secucode.split(".")[0]
    prof = fetch_profile(code6, refresh=refresh)
    stmts = fetch_statements(secucode, years, refresh=refresh)

    # 三张表按年份索引
    by_year = {}
    for table, rows in stmts.items():
        for row in rows:
            y = _year_of(row)
            if not y:
                continue
            by_year.setdefault(y, {})[table] = row
    if not by_year:
        raise RuntimeError("接口未返回任何年报数据：%s" % secucode)

    periods = sorted(by_year)[-years:]

    financials = {}
    source_fields = {}
    for b_key, candidates in FM.EM_TO_B.items():
        cells = {}
        used = None
        for y in periods:
            row = by_year.get(y, {}).get(_table_of(b_key))
            if not row:
                continue
            val, field = _pick(row, candidates)
            if val is None and b_key in FM.EM_SUM:
                vals = [row.get(f) for f in FM.EM_SUM[b_key]]
                vals = [v for v in vals if v is not None]
                val = sum(vals) if vals else None
                field = "+".join(f for f in FM.EM_SUM[b_key] if row.get(f) is not None) or None
            if val is None:
                cells[y] = {"value": None, "unit": "元", "status": "not_found",
                            "source_type": "online", "source_field": None,
                            "source": "东方财富·F10 财务报表", "page": None}
                continue
            used = field
            cells[y] = {
                "value": float(val),
                "unit": "元",
                "status": "found",
                "source_type": "online",
                "source_field": field,
                "source": "东方财富·F10 财务报表（年报）",
                "page": None,
                "source_url": "https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html?type=web&code=%s" % secucode,
            }
        if cells and any(c["value"] is not None for c in cells.values()):
            financials[b_key] = cells
            source_fields[b_key] = used

    missing = [f for f in FM.B_FIELDS if f not in financials]

    return {
        "schema_version": "finradar.extraction/2.0",
        "meta": {
            "periods": periods,
            "default_unit": "元",
            "currency": "CNY",
            "source_mode": "online",
            "data_source": "eastmoney",
            "data_as_of": _dt.date.today().isoformat(),
            "amount_unit": "元",
            "consolidated": True,
            "industry": prof.get("BOARD_NAME") or None,
            "note": "在线模式：无页码，出处为数据源字段与链接",
            # 在线源只有「货币资金」，没有「现金及现金等价物」，两者不同源。
            # 引擎据此把现金净变动勾稽判为「口径不成立」，而不是「不平」。
            "alignment_flags": {"cash_bridge": "not_comparable"},
        },
        "company": {
            "name": prof.get("SECURITY_NAME_ABBR") or code6,
            "ticker": secucode,
            "industry": prof.get("BOARD_NAME") or None,
            "report_period": periods[-1] if periods else None,
        },
        "financials": financials,
        "sources": [
            {
                "source_type": "online",
                "source": "东方财富·F10 财务报表（年报）",
                "source_field": field,
                "metric": key,
                "source_url": "https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html?type=web&code=%s" % secucode,
                "retrieved_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "purpose": "财务数据",
            }
            for key, field in source_fields.items() if field
        ],
        "extraction_meta": {
            "fetcher": "data-bridge/fetch_eastmoney.py",
            "periods": periods,
            "given_count": len(financials),
            "missing_fields": missing,
            "online_has_no_page": True,
        },
    }


def _table_of(b_key: str) -> str:
    """判断某 B 字段来自哪张表。"""
    cf = {"ocf", "cf_investing", "cf_financing", "capex", "cash_received_from_sales",
          "interest_paid", "dividend_paid", "cf_cash_end", "depreciation_amortization"}
    inc = {"revenue", "cost_of_revenue", "operating_profit", "pretax_profit",
           "income_tax_expense", "net_income", "net_income_parent",
           "net_income_deducted", "selling_expense", "admin_expense", "rd_expense",
           "finance_expense", "interest_expense", "impairment_loss"}
    if b_key in cf:
        return "cashflow"
    if b_key in inc:
        return "income"
    return "balance"


# --------------------------------------------------------------------------- #
# 命令行
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="股票代码 → B 输入 JSON（东方财富公开接口）")
    ap.add_argument("--code", help="6 位股票代码，如 600519")
    ap.add_argument("--codes", help="多个代码，逗号分隔")
    ap.add_argument("--years", type=int, default=3, help="取几期年报，默认 3")
    ap.add_argument("--out", help="单代码输出路径")
    ap.add_argument("--out-dir", help="多代码输出目录")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存重新抓取")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    codes = []
    if args.code:
        codes = [args.code]
    elif args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    else:
        ap.error("需要 --code 或 --codes")

    for code in codes:
        try:
            obj = build_b_input(code, years=args.years, refresh=args.refresh)
        except Exception as e:
            print("[FAIL] %s -> %s" % (code, e), file=sys.stderr)
            continue
        periods = obj["meta"]["periods"]
        given = obj["extraction_meta"]["given_count"]
        if len(codes) == 1 and args.out:
            out = args.out
        else:
            base = args.out_dir or os.path.dirname(os.path.abspath(__file__))
            os.makedirs(base, exist_ok=True)
            out = os.path.join(base, "input_%s.json" % code)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        if not args.quiet:
            print("[OK] %s %s  期间 %s  科目 %d  缺失 %d -> %s" % (
                code, obj["company"]["name"], "-".join(periods), given,
                len(obj["extraction_meta"]["missing_fields"]), out))


if __name__ == "__main__":
    main()
