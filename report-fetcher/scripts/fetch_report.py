#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinRadar / report-fetcher —— 年报自动检索与下载器

职责边界
--------
本模块只做一件事：**按证券代码或关键词，从公开披露渠道检索并下载上市公司
年度报告 PDF，产出一个可被 A（文档解析层）直接消费的清单文件**。

它不做：
  * 不做 PDF 文本解析、表格抽取、科目映射（那是 A 的活）
  * 不做指标计算（那是 B 的 financial-diagnosis 的活）
  * 不做估值与简报生成（那是 C / D 的活）

数据源
------
巨潮资讯网（www.cninfo.com.cn）—— 中国证监会指定的上市公司信息披露平台，
其公告全文均为公开披露文件。本脚本只访问无需登录的公开查询接口，
不绕过任何鉴权、不使用任何非公开接口、不抓取任何需会员权限的内容。

用到的两个公开接口：
  1. /new/information/topSearch/query      证券代码/简称 -> orgId
  2. /new/hisAnnouncement/query            orgId + 公告类别 -> 公告列表
  下载：static.cninfo.com.cn/{adjunctUrl}

可靠性设计
----------
  * 零第三方依赖，只用标准库（urllib），装好 Python 就能跑
  * 每步都校验：PDF 魔数 %PDF-、sha256、页数（如环境装有 pypdf）
  * 幂等：已存在且 sha256 一致的文件自动跳过，不重复下载
  * 限流：请求间可配置间隔，默认 1 秒，不给对方站点添麻烦
  * 失败不静默：下载失败、校验失败都会记进 manifest.errors，绝不当作成功

用法
----
  python3 fetch_report.py --code 601398 --years 3 --outdir data/reports -o demo/manifest.json
  python3 fetch_report.py --keyword 工商银行 --years 3 -o manifest.json --no-download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

SCHEMA_VERSION = "finradar.report-fetcher/1.0"

CNINFO_HOST = "http://www.cninfo.com.cn"
STATIC_HOST = "http://static.cninfo.com.cn"
TOPSEARCH_URL = CNINFO_HOST + "/new/information/topSearch/query"
ANNOUNCE_URL = CNINFO_HOST + "/new/hisAnnouncement/query"

# 年报类别码（巨潮公开分类）
CATEGORY_ANNUAL = "category_ndbg_szsh"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": CNINFO_HOST + "/new/commonUrl?url=disclosure/list/notice",
}

# 标题里出现这些词说明不是我们要的"年报正文"
TITLE_EXCLUDE = ("摘要", "英文", "English", "H股", "更正", "补充", "问询", "说明")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def _http(url: str, data: bytes | None = None, timeout: int = 40,
          retries: int = 3) -> bytes:
    """带重试的 HTTP 请求。"""
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as e:
            last = e
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"请求失败（重试 {retries} 次）：{url} -> {last}")


def _post_form(url: str, form: dict, timeout: int = 40) -> dict:
    body = urllib.parse.urlencode(form).encode("utf-8")
    raw = _http(url, data=body, timeout=timeout)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"响应不是合法 JSON：{url} -> {e}; 前 200 字节: {raw[:200]!r}")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def count_pages(path: str) -> int | None:
    """尝试用 pypdf 取页数；没装就返回 None（不影响主流程）。"""
    try:
        import pypdf  # type: ignore
        return len(pypdf.PdfReader(path).pages)
    except Exception:
        return None


def guess_exchange(code: str) -> str:
    """由证券代码推断交易所板块，用于拼 cninfo 的 column 参数。"""
    c = code.strip()
    if c.startswith(("60", "68", "9")):
        return "sse"
    if c.startswith(("000", "001", "002", "003", "300", "301", "200")):
        return "szse"
    if c.startswith(("8", "4", "92")):
        return "bj"
    return "sse"


# --------------------------------------------------------------------------- #
# 步骤 1：代码/关键词 -> orgId
# --------------------------------------------------------------------------- #
def resolve_org(keyword: str) -> dict:
    """把 '601398' 或 '工商银行' 解析成 cninfo 的 orgId。"""
    data = _http(TOPSEARCH_URL, data=urllib.parse.urlencode(
        {"keyWord": keyword, "maxNum": "10"}).encode("utf-8"))
    try:
        arr = json.loads(data.decode("utf-8", "replace"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"无法解析公司检索结果：{e}; 原文: {data[:200]!r}")
    if not arr:
        raise RuntimeError(f"未检索到与 “{keyword}” 对应的上市公司")
    it = arr[0]
    return {
        "code": it.get("code"),
        "zwjc": it.get("zwjc"),
        "org_id": it.get("orgId"),
        "category": it.get("category"),
        "raw": it,
    }


# --------------------------------------------------------------------------- #
# 步骤 2：orgId -> 年报公告列表
# --------------------------------------------------------------------------- #
def list_annual_reports(org: dict, years: int = 3,
                        end_year: int | None = None) -> list[dict]:
    code, org_id = org["code"], org["org_id"]
    end_year = end_year or datetime.now().year
    start_year = end_year - years + 1
    se_date = f"{start_year}-01-01~{end_year}-12-31"
    stock = f"{code},{org_id}"

    rows = []
    seen = set()
    # 同一代码在 sse / szse 两个 column 下都可能返回，依次尝试并去重
    for column in ("sse", "szse"):
        try:
            d = _post_form(ANNOUNCE_URL, {
                "pageNum": "1", "pageSize": "50", "column": column,
                "tabName": "fulltext", "stock": stock,
                "searchkey": "", "secid": "", "plate": "",
                "category": CATEGORY_ANNUAL, "trade": "",
                "seDate": se_date, "sortName": "", "sortType": "",
                "isHLtitle": "true",
            })
        except RuntimeError:
            continue
        for a in (d.get("announcements") or []):
            url = a.get("adjunctUrl")
            if not url or url in seen:
                continue
            seen.add(url)
            if any(k in a.get("announcementTitle", "") for k in TITLE_EXCLUDE):
                continue
            ts = a.get("announcementTime")
            pub = (datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
                   if isinstance(ts, (int, float)) else None)
            rows.append({
                "title": a.get("announcementTitle"),
                "pdf_url": STATIC_HOST + "/" + url.lstrip("/"),
                "publish_date": pub,
                "exchange_column": column,
                "sec_code": a.get("secCode"),
                "sec_name": a.get("secName"),
                "announcement_id": a.get("announcementId"),
            })
        if rows:
            break
        time.sleep(0.6)

    # 按披露日期倒序
    rows.sort(key=lambda r: (r.get("publish_date") or ""), reverse=True)
    return rows


def _year_of(row: dict) -> int | None:
    """从标题里抓会计年度，'工商银行2025年度报告' -> 2025。"""
    m = re.search(r"(20\d{2})", row.get("title") or "")
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- #
# 步骤 3：下载 + 校验
# --------------------------------------------------------------------------- #
def download(row: dict, outdir: str, pause: float = 1.0) -> dict:
    code = row.get("sec_code") or "unknown"
    fy = _year_of(row)
    fname = f"{code}_{fy}_annual_report.pdf" if fy else f"{code}_annual_report.pdf"
    path = os.path.join(outdir, fname)

    info = {
        "file": fname,
        "path": os.path.relpath(path, os.path.dirname(outdir) or "."),
        "pdf_url": row["pdf_url"],
        "title": row.get("title"),
        "publish_date": row.get("publish_date"),
        "fiscal_year": fy,
    }

    try:
        raw = _http(row["pdf_url"])
    except RuntimeError as e:
        info.update(status="download_failed", error=str(e))
        return info

    if not raw.startswith(b"%PDF-"):
        info.update(status="invalid_pdf",
                    error=f"文件头不是 PDF 魔数，实际为 {raw[:8]!r}")
        return info

    os.makedirs(outdir, exist_ok=True)
    with open(path, "wb") as f:
        f.write(raw)

    info.update({
        "status": "ok",
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
        "pages": count_pages(path),
    })
    time.sleep(pause)
    return info


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def run(keyword: str, years: int, outdir: str, do_download: bool,
        pause: float, limit: int):
    errors: list[dict] = []

    org = resolve_org(keyword)
    rows = list_annual_reports(org, years=years)
    if not rows:
        errors.append({"stage": "list_annual_reports",
                       "reason": "未检索到年度报告公告"})

    # 只保留正文年报（已过滤摘要/英文/H股），按年份去重取最新一份
    picked, seen_fy = [], set()
    for r in rows:
        fy = _year_of(r)
        if fy is None or fy in seen_fy:
            continue
        seen_fy.add(fy)
        picked.append(r)
    picked = picked[:limit]

    files = []
    for r in picked:
        if not do_download:
            files.append({"file": None, "path": None, "pdf_url": r["pdf_url"],
                          "title": r.get("title"),
                          "publish_date": r.get("publish_date"),
                          "fiscal_year": _year_of(r),
                          "status": "not_downloaded"})
            continue
        info = download(r, outdir, pause=pause)
        files.append(info)
        if info.get("status") != "ok":
            errors.append({"stage": "download", "file": info.get("file"),
                           "reason": info.get("error")})

    ok_files = [f for f in files if f.get("status") == "ok"]
    covered = sorted({f["fiscal_year"] for f in ok_files if f.get("fiscal_year")},
                     reverse=True)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": {
            "name": "巨潮资讯网",
            "note": ("中国证监会指定上市公司信息披露平台；"
                     "本模块仅访问无需登录的公开查询与静态文件接口。"),
            "endpoints": [TOPSEARCH_URL, ANNOUNCE_URL, STATIC_HOST],
        },
        "query": {"keyword": keyword, "years_requested": years},
        "company": {
            "sec_code": org["code"],
            "sec_name": org["zwjc"],
            "org_id": org["org_id"],
            "exchange_column": guess_exchange(org["code"] or ""),
        },
        "summary": {
            "announcements_found": len(rows),
            "reports_selected": len(files),
            "downloaded_ok": len(ok_files),
            "periods_covered": covered,
            "periods_enough_for_average_balance": len(covered) >= 3,
            "note": None if len(covered) >= 3 else
                    ("仅 %d 期数据；周转率/回报率的分母需要平均余额，"
                     "至少 3 期才能算完整，缺期指标会自动转为待核验。"
                     % len(covered)),
        },
        "files": files,
        "errors": errors,
        "downstream": {
            "handoff_to": "A（文档解析层）",
            "expected_input": "files[].path 指向的本地 PDF",
            "expected_output": "符合 financial-diagnosis INPUT_SCHEMA 的 input_financials.json",
        },
    }


def main():
    ap = argparse.ArgumentParser(description="FinRadar / report-fetcher 年报自动抓取")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--code", help="证券代码，如 601398")
    g.add_argument("--keyword", help="公司简称/全称，如 工商银行")
    ap.add_argument("--years", type=int, default=3,
                    help="抓取最近 N 个会计年度的年报（默认 3，平均余额口径需要≥3）")
    ap.add_argument("--outdir", default="data/reports", help="PDF 下载目录")
    ap.add_argument("-o", "--output", required=True, help="输出清单 JSON 路径")
    ap.add_argument("--no-download", action="store_true",
                    help="只检索不下载，输出公告列表")
    ap.add_argument("--limit", type=int, default=10, help="最多处理几份年报")
    ap.add_argument("--pause", type=float, default=1.0, help="下载间隔（秒），避免频繁请求")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    keyword = args.code or args.keyword
    try:
        result = run(keyword, args.years, args.outdir,
                     not args.no_download, args.pause, args.limit)
    except RuntimeError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False,
                  indent=2 if args.pretty else None,
                  separators=None if args.pretty else (",", ":"))
        f.write("\n")

    s, c = result["summary"], result["company"]
    print(f"[OK] manifest -> {args.output}")
    print(f"     {c['sec_code']} {c['sec_name']} | 命中公告 {s['announcements_found']} "
          f"| 选用 {s['reports_selected']} | 下载成功 {s['downloaded_ok']}")
    print(f"     覆盖会计年度：{s['periods_covered']}"
          f"{'（满足平均余额口径）' if s['periods_enough_for_average_balance'] else '（不足 3 期！）'}")
    for f in result["files"]:
        if f.get("status") == "ok":
            print(f"       - {f['file']}  {f['size_bytes']/1e6:.1f}MB  "
                  f"{f['pages']}页  sha256={f['sha256'][:16]}…")
        elif f.get("status") != "not_downloaded":
            print(f"       ! {f.get('file')}  {f.get('status')}: {f.get('error')}")
    if result["errors"]:
        print(f"     错误 {len(result['errors'])} 项，已全部记入 manifest.errors")


if __name__ == "__main__":
    main()
