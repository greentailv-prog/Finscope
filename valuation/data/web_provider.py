"""联网搜索取数：搜索 → 找年报 PDF → 下载 → 解析财务与分部。

设计原则：
  · 不依赖付费搜索 API；默认用 DuckDuckGo HTML（无密钥），
    也支持 Tavily / SerpAPI / Bing / 自建搜索端点；
  · 优先找**官方年报 PDF**（巨潮资讯等），从原文抽数，而不是从新闻摘要猜数；
  · 抽不到就明确返回「解析失败 + 证据」，由 Agent/D 复核，不编数字；
  · 所有结果带 URL、报告期、页码/表名，写入 sources。

依赖：requests、beautifulsoup4、pandas、lxml、pdfplumber。
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

import requests

from . import cache
from .sources import source

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "web"
PDF_DIR = CACHE_DIR / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

SEARCH_TIMEOUT = 25
PAGE_TIMEOUT = 30


def _session() -> requests.Session:
    """默认不走系统代理：Windows 上代理软件挂掉时，requests 会直接连不上。

    需要走代理时设置 FINSCOPE_HTTP_PROXY（如 http://127.0.0.1:7897）。
    """
    s = requests.Session()
    s.trust_env = False
    proxy = os.environ.get("FINSCOPE_HTTP_PROXY")
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


# ======================================================================
# 一、搜索
# ======================================================================


def _decode_ddg(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        qs = parse_qs(urlparse(href).query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    return href


def _ddg_search(query: str, max_results: int = 8) -> list[dict]:
    r = _session().get("https://html.duckduckgo.com/html/", params={"q": query},
                       headers={"User-Agent": UA}, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "lxml")
    out = []
    for block in soup.select(".result"):
        a = block.select_one(".result__a")
        if not a:
            continue
        snippet = block.select_one(".result__snippet")
        out.append({
            "title": a.get_text(" ", strip=True),
            "url": _decode_ddg(a.get("href") or ""),
            "snippet": snippet.get_text(" ", strip=True) if snippet else "",
            "engine": "DuckDuckGo",
        })
        if len(out) >= max_results:
            break
    return out


def _tavily_search(query: str, max_results: int = 8) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    r = _session().post("https://api.tavily.com/search",
                        json={"api_key": key, "query": query, "max_results": max_results,
                              "search_depth": "advanced", "include_answer": False},
                        timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    return [{"title": x.get("title", ""), "url": x.get("url", ""),
             "snippet": x.get("content", ""), "engine": "Tavily"}
            for x in r.json().get("results", [])]


def _serpapi_search(query: str, max_results: int = 8) -> list[dict]:
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        return []
    r = _session().get("https://serpapi.com/search.json",
                       params={"q": query, "api_key": key, "num": max_results, "hl": "zh-cn"},
                       timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    return [{"title": x.get("title", ""), "url": x.get("link", ""),
             "snippet": x.get("snippet", ""), "engine": "SerpAPI"}
            for x in r.json().get("organic_results", [])]


def _bing_search(query: str, max_results: int = 8) -> list[dict]:
    key = os.environ.get("BING_SEARCH_KEY")
    endpoint = os.environ.get("BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search")
    if not key:
        return []
    r = _session().get(endpoint, params={"q": query, "count": max_results, "mkt": "zh-CN"},
                       headers={"Ocp-Apim-Subscription-Key": key}, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    return [{"title": x.get("name", ""), "url": x.get("url", ""),
             "snippet": x.get("snippet", ""), "engine": "Bing"}
            for x in r.json().get("webPages", {}).get("value", [])]


def search(query: str, max_results: int = 8) -> dict:
    """联网搜索。返回 {ok, engine, results, error}。"""
    engines = [
        ("Tavily", _tavily_search),
        ("SerpAPI", _serpapi_search),
        ("Bing", _bing_search),
        ("DuckDuckGo", _ddg_search),
    ]
    errors = []
    for name, fn in engines:
        try:
            results = fn(query, max_results)
            if results:
                return {"ok": True, "engine": name, "query": query, "results": results}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:80]}")
    return {"ok": False, "query": query, "results": [], "error": "；".join(errors) or "无搜索结果"}


# ======================================================================
# 二、找年报 PDF
# ======================================================================


def _looks_like_pdf(url: str, title: str = "") -> bool:
    u = (url or "").lower()
    t = (title or "").lower()
    return u.endswith(".pdf") or ".pdf" in u or "年度报告" in t or "年报" in t


def _find_pdf_links(html: str, base_url: str) -> list[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                p = urlparse(base_url)
                href = f"{p.scheme}://{p.netloc}{href}"
            out.append(href)
    return list(dict.fromkeys(out))


_CNINFO_ORG: dict[str, str] | None = None


def _cninfo_org_map() -> dict[str, str]:
    """巨潮资讯深市 orgId 映射；沪市用 gssh 前缀即可。"""
    global _CNINFO_ORG
    if _CNINFO_ORG is not None:
        return _CNINFO_ORG
    mapping = {}
    try:
        r = _session().get("http://www.cninfo.com.cn/new/data/szse_stock.json",
                           headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        for row in (r.json().get("stockList") or []):
            code = str(row.get("code") or "")
            org = str(row.get("orgId") or "")
            if code and org:
                mapping[code] = org
    except Exception:  # noqa: BLE001
        pass
    _CNINFO_ORG = mapping
    return mapping


def _cninfo_stock(ticker: str) -> str:
    code = str(ticker).strip()
    for p in ("SH", "SZ", "BJ"):
        if code.upper().startswith(p):
            code = code[2:]
    code = code.zfill(6)
    if code[0] == "6":
        return f"{code},gssh0{code}"
    org = _cninfo_org_map().get(code)
    if org:
        return f"{code},{org}"
    if code[0] in ("0", "3"):
        return f"{code},gssz0{code}"
    return f"{code},gsbj0{code}"


def find_annual_report_cninfo(ticker: str, year: int) -> dict:
    """巨潮资讯年报检索（结构化、最可靠）。"""
    if not ticker:
        return {"ok": False, "error": "缺少代码，无法查询巨潮资讯"}
    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    headers = {
        "User-Agent": UA,
        "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
        "X-Requested-With": "XMLHttpRequest",
    }
    data = {
        "pageNum": "1", "pageSize": "30", "column": "szse", "tabName": "fulltext",
        "plate": "", "stock": _cninfo_stock(ticker), "searchkey": "", "secid": "",
        "category": "category_ndbg_szsh", "trade": "", "seDate": "",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    try:
        r = _session().post(url, data=data, headers=headers, timeout=30)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"巨潮资讯查询失败：{type(exc).__name__}: {str(exc)[:100]}"}
    for a in payload.get("announcements") or []:
        title = str(a.get("announcementTitle") or "")
        if str(year) not in title or "年度报告" not in title:
            continue
        if any(k in title for k in ("摘要", "英文", "已取消", "更正")):
            continue
        adj = str(a.get("adjunctUrl") or "")
        if not adj.lower().endswith(".pdf"):
            continue
        return {
            "ok": True,
            "url": "https://static.cninfo.com.cn/" + adj.lstrip("/"),
            "title": title,
            "query": f"cninfo:{ticker}:{year}",
            "engine": "巨潮资讯",
            "announcement_time": a.get("announcementTime"),
        }
    return {"ok": False, "error": f"巨潮资讯未找到 {ticker} {year} 年度报告"}


def company_announcements(ticker: str, limit: int = 8) -> list[dict]:
    """巨潮资讯最新公告（结构化，不依赖通用搜索）。"""
    if not ticker:
        return []
    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    headers = {
        "User-Agent": UA,
        "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
        "X-Requested-With": "XMLHttpRequest",
    }
    data = {
        "pageNum": "1", "pageSize": "30", "column": "szse", "tabName": "fulltext",
        "plate": "", "stock": _cninfo_stock(ticker), "searchkey": "", "secid": "",
        "category": "", "trade": "", "seDate": "", "sortName": "", "sortType": "",
        "isHLtitle": "true",
    }
    try:
        r = _session().post(url, data=data, headers=headers, timeout=30)
        payload = r.json()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for a in payload.get("announcements") or []:
        title = str(a.get("announcementTitle") or "").strip()
        adj = str(a.get("adjunctUrl") or "")
        if not title or not adj:
            continue
        ts = a.get("announcementTime")
        date_text = ""
        if isinstance(ts, (int, float)):
            from datetime import datetime
            date_text = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        out.append({
            "title": title,
            "url": "https://static.cninfo.com.cn/" + adj.lstrip("/"),
            "snippet": f"{title}（{date_text}）",
            "date": date_text,
            "engine": "巨潮资讯",
        })
        if len(out) >= limit:
            break
    return out


def find_annual_report(company_name: str, year: int, ticker: str = "") -> dict:
    """定位某一年度报告 PDF：巨潮资讯结构化检索优先，联网搜索兜底。"""
    if ticker:
        found = find_annual_report_cninfo(ticker, year)
        if found.get("ok"):
            return found
    queries = [
        f"{company_name} {year} 年度报告 PDF 巨潮资讯",
        f"{company_name} {year} 年年度报告 营业收入",
        f"{ticker} {year} 年度报告 site:static.cninfo.com.cn",
    ]
    for q in queries:
        res = search(q, max_results=10)
        for item in res.get("results", []):
            url = item.get("url") or ""
            title = item.get("title") or ""
            if _looks_like_pdf(url, title) and url.lower().startswith("http"):
                if ".pdf" in url.lower():
                    return {"ok": True, "url": url, "title": title, "query": q,
                            "results": res.get("results", [])}
                # 落地页：抓一次找 PDF 链接
                page = fetch_page(url)
                for pdf in _find_pdf_links(page.get("html", ""), url):
                    return {"ok": True, "url": pdf, "title": title, "query": q,
                            "results": res.get("results", [])}
    return {"ok": False, "error": f"未找到 {company_name} {year} 年度报告 PDF",
            "queries": queries}


# ======================================================================
# 三、抓网页 / 下载 PDF
# ======================================================================


def fetch_page(url: str) -> dict:
    """抓网页，返回文本、表格、HTML。"""
    try:
        r = _session().get(url, headers={"User-Agent": UA}, timeout=PAGE_TIMEOUT)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": url, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        return {"ok": True, "url": url, "type": "pdf", "content": r.content}
    r.encoding = r.apparent_encoding or r.encoding or "utf-8"
    html = r.text
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    tables = extract_tables(html)
    return {"ok": True, "url": url, "type": "html", "html": html, "text": text,
            "tables": tables, "title": soup.title.get_text(strip=True) if soup.title else ""}


def extract_tables(html: str) -> list[dict]:
    import pandas as pd
    from io import StringIO
    out = []
    try:
        frames = pd.read_html(StringIO(html))
    except Exception:  # noqa: BLE001
        return out
    for df in frames:
        if df is None or df.empty:
            continue
        cols = [str(c).replace("\n", " ").strip() for c in df.columns]
        rows = []
        for _, row in df.iterrows():
            rows.append([str(v).replace("\n", " ").strip() if v is not None else ""
                         for v in row.tolist()])
        out.append({"columns": cols, "rows": rows})
        if len(out) >= 30:
            break
    return out


def download_pdf(url: str, stem: str) -> Path:
    target = PDF_DIR / f"{stem}.pdf"
    if target.exists() and target.stat().st_size > 10_000:
        return target
    r = _session().get(url, headers={"User-Agent": UA}, timeout=90)
    r.raise_for_status()
    target.write_bytes(r.content)
    return target


# ======================================================================
# 四、解析年报
# ======================================================================

_LABEL_ALIASES = {
    "revenue_total": ["营业总收入"],
    "revenue": ["营业总收入", "营业收入"],
    "cogs": ["营业成本"],
    "operating_profit": ["营业利润"],
    "pretax_income": ["利润总额"],
    "tax_provision": ["所得税费用"],
    "net_income": ["净利润"],
    "net_income_parent": ["归属于母公司股东的净利润", "归属于母公司所有者的净利润",
                          "归属于母公司净利润", "本行股东的净利润", "归属于本行股东的净利润"],
    "finance_expense": ["财务费用", "财务收入"],
    "interest_expense": ["利息费用"],
    "eps": ["基本每股收益", "基本及稀释每股收益"],
    "cfo": ["经营活动产生的现金流量净额"],
    "capex": ["购建固定资产、无形资产和其他长期资产支付的现金",
              "购建固定资产、无形资产和其他长期资产所支付的现金"],
    "dividends_paid": ["分配股利、利润或偿付利息支付的现金"],
    "dep_fixed": ["固定资产折旧、油气资产折耗、生产性生物资产折旧"],
    "dep_use_right": ["使用权资产摊销"],
    "amort_intangible": ["无形资产摊销"],
    "amort_lt_prepaid": ["长期待摊费用摊销"],
    "da_total": ["折旧和摊销"],
    "cash": ["货币资金", "现金"],
    "short_debt": ["短期借款"],
    "long_debt": ["长期借款"],
    "bond": ["应付债券"],
    "current_portion": ["一年内到期的非流动负债"],
    "minority": ["少数股东权益"],
    "total_equity": ["所有者权益（或股东权益）合计", "所有者权益(或股东权益)合计",
                     "股东权益合计", "所有者权益合计"],
    "total_equity_parent": ["归属于母公司所有者权益合计", "归属于母公司股东权益合计",
                            "归属于本行股东权益合计"],
    "total_assets": ["资产总计", "资产合计", "负债及股东权益总计"],
    "shares": ["股本", "实收资本（或股本）", "实收资本(或股本)"],
    "receivables": ["应收账款", "应收票据及应收账款"],
    "inventory": ["存货"],
    "payables": ["应付账款", "应付票据及应付账款"],
}


def _norm_label(text) -> str:
    text = str(text or "")
    text = text.replace("\n", "").replace(" ", "").replace("　", "")
    text = text.replace("（", "(").replace("）", ")").replace("：", ":")
    text = re.sub(r"^[一二三四五六七八九十]+、", "", text)
    text = re.sub(r"^\([一二三四五六七八九十]+\)", "", text)
    text = re.sub(r"^\d+[.、]", "", text)
    text = text.replace("其中:", "").replace("减:", "").replace("加:", "")
    return text.strip(":： ")


def _num(text) -> float | None:
    if text is None:
        return None
    s = str(text).strip().replace(",", "").replace("，", "")
    s = s.replace("—", "").replace("－", "-").replace("(", "-").replace(")", "")
    if s in ("", "-", "--", "不适用", "nan", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _segment_name(line: str) -> str:
    name = re.sub(r"[\d,\.%()\-]+", " ", line)
    name = name.replace("其中", "").replace("：", "").replace(":", "")
    return re.sub(r"\s+", " ", name).strip()


def _parse_segment_text_page(text: str, unit: float, report_year: int,
                             page_no: int) -> list[dict]:
    """从「分产品」文字段解析分部（适用于没有表格边框的年报）。"""
    rows = []
    in_product = False
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("分产品"):
            in_product = True
            continue
        if any(s.startswith(k) for k in ("分地区", "分销售模式", "分行业")):
            in_product = False
            continue
        if not in_product:
            continue
        if s.startswith("合计") or "营业收入" in s or "营业成本" in s:
            continue
        nums = _text_numbers(s)
        if len(nums) < 6:
            continue
        revenue, cost = nums[0] * unit, nums[1] * unit
        margin = nums[2] / 100 if abs(nums[2]) > 1 else nums[2]
        if revenue <= 0 or cost <= 0 or cost > revenue * 1.5:
            continue
        name = _segment_name(s)
        if not name:
            continue
        rows.append({
            "name": name, "level": "top", "parent": "",
            "revenue": revenue, "cost": cost,
            "gross_profit": revenue - cost, "gross_margin": margin,
            "revenue_share": None, "period": f"{report_year}-12-31",
            "source": f"年报第 {page_no} 页·分产品",
        })
    return _drop_subtotal_rows(rows)


def _drop_subtotal_rows(rows: list[dict]) -> list[dict]:
    """如果某一行收入≈其他若干行之和，说明它是父级小计，剔除它避免重复计算。"""
    from itertools import combinations
    if len(rows) < 3:
        return rows
    drop = set()
    for i, parent in enumerate(rows):
        rev = parent.get("revenue")
        if not rev or rev <= 0:
            continue
        others = [(j, r) for j, r in enumerate(rows)
                  if j != i and (r.get("revenue") or 0) < rev * 0.99]
        found = False
        for size in range(2, min(len(others), 6) + 1):
            for combo in combinations(others, size):
                total = sum((r.get("revenue") or 0) for _, r in combo)
                if abs(total - rev) / rev < 0.01:
                    drop.add(i)
                    found = True
                    break
            if found:
                break
    return [r for i, r in enumerate(rows) if i not in drop]


def _iter_tables(pdf):
    for page_no, page in enumerate(pdf.pages, start=1):
        text = page.extract_text() or ""
        for table in page.extract_tables() or []:
            if table:
                yield page_no, text, table


def _page_unit(text: str) -> float:
    if "百万元" in text:
        return 1e6
    if "单位：万元" in text or "单位:万元" in text:
        return 1e4
    if "单位：千元" in text or "单位:千元" in text or "金额单位为人民币千元" in text:
        return 1e3
    if "单位：亿元" in text or "单位:亿元" in text:
        return 1e8
    return 1.0


def _text_numbers(line: str) -> list[float]:
    """从一行文字里取数值，过滤掉「四(1)」这类附注编号。"""
    tokens = re.findall(r"\(?-?\d[\d,]*\.?\d*\)?", line)
    out = []
    for t in tokens:
        v = _num(t)
        if v is None:
            continue
        if "," in t or "." in t or abs(v) >= 1000:
            out.append(v)
    return out


def _year_cols(table: list[list], report_year: int) -> tuple[int, int | None]:
    """从表头找「本期/上期」列；找不到时按列数推断。"""
    for row in table[:4]:
        cells = [_norm_label(c) for c in row]
        cur = next((i for i, c in enumerate(cells)
                    if str(report_year) in c or "本期" in c or "期末" in c), None)
        prior = next((i for i, c in enumerate(cells)
                      if str(report_year - 1) in c or "上期" in c or "期初" in c), None)
        if cur is not None:
            return cur, prior
    width = max((len(r) for r in table if r), default=0)
    if width >= 4:
        return 2, 3
    if width == 3:
        return 1, 2
    return 1, None


def _label_matches(label: str, aliases: list[str]) -> bool:
    for alias in aliases:
        a = _norm_label(alias)
        if label == a or label.startswith(a):
            return True
    return False


def _find_value(row: list, aliases: list[str], idx: int | None) -> float | None:
    if not row or idx is None or len(row) <= idx:
        return None
    label = _norm_label(row[0])
    if _label_matches(label, aliases):
        return _num(row[idx])
    return None


def parse_annual_report(pdf_path: str | Path, report_year: int) -> dict:
    """从年报 PDF 抽财务与分部。返回 {ok, years:{year:{...}}, segments, ...}。"""
    import pdfplumber
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {"ok": False, "error": f"PDF 不存在：{pdf_path}"}

    # (priority, value)：主表 priority=0，附注 priority=1，主表优先
    picked: dict[int, dict[str, tuple[int, float]]] = {report_year: {}, report_year - 1: {}}
    segments = []
    segment_pages = []
    all_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            all_text.append(text)
            unit = _page_unit(text)
            is_main = (
                "合并及公司资产负债表" in text
                or "合并及公司利润表" in text
                or "合并及公司现金流量表" in text
                or ("合并资产负债表" in text and f"{report_year}年12月31日" in text)
                or ("合并资产负债表(续)" in text or "合并资产负债表（续）" in text)
                or ("合并利润表" in text and (f"{report_year}年1—12月" in text
                                              or f"{report_year}年12月31日止年度" in text))
                or ("合并现金流量表" in text and (f"{report_year}年1—12月" in text
                                                  or f"{report_year}年12月31日止年度" in text))
                or "负债及股东权益总计" in text
                or "现金流量表补充资料" in text
                or "将净利润调节为经营活动现金流量" in text
            ) and ("财务报表附注" not in text[:300] or "现金流量表补充资料" in text)
            priority = 0 if is_main else 1
            if os.environ.get("FINSCOPE_DEBUG_PARSER") and page_no in (135, 136, 137):
                print(f"[page] {page_no} is_main={is_main} chars={len(text)} tables={len(page.extract_tables() or [])}")
            tables = page.extract_tables() or []
            for table in tables:
                if not table:
                    continue
                cur_idx, prior_idx = _year_cols(table, report_year)

                # ---- 分部：只在「主营业务分产品情况」段落里取 ----
                section = None
                for r in table:
                    if not r:
                        continue
                    label = _norm_label(r[0])
                    if "主营业务分产品情况" in label:
                        section = "product"
                        continue
                    if "主营业务分" in label and "情况" in label:
                        section = None
                        continue
                    if section != "product":
                        continue
                    if not label or label in ("分产品", "合计", "营业收入", "营业成本", "毛利率(%)"):
                        continue
                    nums = [_num(c) for c in r[1:]]
                    nums = [v for v in nums if v is not None]
                    if len(nums) < 2:
                        continue
                    revenue = nums[0] * unit
                    cost = nums[1] * unit
                    margin = None
                    if len(nums) > 2:
                        margin = nums[2] / 100 if abs(nums[2]) > 1 else nums[2]
                    if revenue <= 0:
                        continue
                    segments.append({
                        "name": label,
                        "level": "top",
                        "parent": "",
                        "revenue": revenue,
                        "cost": cost,
                        "gross_profit": revenue - cost,
                        "gross_margin": margin,
                        "revenue_share": None,
                        "period": f"{report_year}-12-31",
                        "source": f"年报第 {page_no} 页·主营业务分产品",
                    })

                # ---- 财务：逐行匹配，主表优先 ----
                for row in table:
                    if not row:
                        continue
                    for year, idx in ((report_year, cur_idx), (report_year - 1, prior_idx)):
                        if year not in picked:
                            continue
                        for key, aliases in _LABEL_ALIASES.items():
                            v = _find_value(row, aliases, idx)
                            if v is None:
                                continue
                            v = v * unit
                            if key in ("cogs", "capex", "tax_provision"):
                                v = abs(v)
                            if key == "finance_expense" and "财务收入" in _norm_label(row[0]):
                                v = -abs(v)
                            old = picked[year].get(key)
                            if old is None or priority < old[0]:
                                picked[year][key] = (priority, v)

            # 分部：有些年报没有表格边框，按「分产品」文字段兜底
            segments.extend(_parse_segment_text_page(text, unit, report_year, page_no))

            # 有些年报的报表没有表格边框（extract_tables 为空），按文字行兜底
            if is_main:
                pending = ""
                if os.environ.get("FINSCOPE_DEBUG_PARSER") and page_no == 137:
                    print(f"[textblock] p137 lines={len(text.splitlines())}")
                for line in text.splitlines():
                    if os.environ.get("FINSCOPE_DEBUG_PARSER") and page_no == 137 and "购建" in line:
                        print(f"[raw137] {line!r} nums={_text_numbers(line)}")
                    label = _norm_label(line)
                    if not label:
                        continue
                    nums = _text_numbers(line)
                    if len(nums) < 2:
                        # 标签换行：把没有数字的行攒起来，和下一行拼接后再匹配
                        # 只保留紧邻的上一行，避免把「终止经营净利润」等上一行拼进来
                        pending = label[-80:]
                        continue
                    candidates = [label]
                    if pending:
                        # 只有「上一行本身不是完整科目名」时才拼接，避免
                        # 「营业收入」表头 + 下一行「利息收入」被错误拼成营业收入
                        pending_is_header = any(
                            _label_matches(pending, aliases)
                            for aliases in _LABEL_ALIASES.values()
                        )
                        if not pending_is_header:
                            candidates.insert(0, _norm_label(pending + label))
                        pending = ""
                    if os.environ.get("FINSCOPE_DEBUG_PARSER") and (
                            "购建" in line or "购建" in candidates[0] or label.startswith("现金")):
                        print(f"[line] p{page_no} nums={len(nums)} pending_used={len(candidates) > 1} "
                              f"cands={[c[:70] for c in candidates]} "
                              f"match={any(_label_matches(c, _LABEL_ALIASES['capex']) for c in candidates)}")
                    if len(nums) >= 4:
                        cur_v, prior_v = nums[-4], nums[-3]
                    else:
                        cur_v, prior_v = nums[-2], nums[-1]
                    for cand in candidates:
                        if len(cand) > 120:
                            continue
                        for key, aliases in _LABEL_ALIASES.items():
                            if not _label_matches(cand, aliases):
                                continue
                            for year, raw_v in ((report_year, cur_v), (report_year - 1, prior_v)):
                                if year not in picked:
                                    continue
                                v = abs(raw_v) if key in ("cogs", "capex", "tax_provision") else raw_v
                                if key == "finance_expense" and "财务收入" in cand:
                                    v = -abs(v)
                                # 每股收益是「元/股」，不跟随报表单位缩放
                                v = v if key == "eps" else v * unit
                                old = picked[year].get(key)
                                if old is None or priority < old[0]:
                                    picked[year][key] = (priority, v)
                                    if os.environ.get("FINSCOPE_DEBUG_PARSER"):
                                        print(f"[parser] p{page_no} {year} {key} = {v} (prio {priority})")

    # 分部去重
    seen = set()
    uniq_segments = []
    for s in segments:
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        uniq_segments.append(s)
    total_seg_rev = sum(s["revenue"] for s in uniq_segments) or None
    if total_seg_rev:
        for s in uniq_segments:
            s["revenue_share"] = s["revenue"] / total_seg_rev

    years_data = {}
    for year, vals in picked.items():
        if not vals:
            continue
        clean = {k: v for k, (_, v) in vals.items()}
        if clean.get("revenue_total") is not None:
            clean["revenue"] = clean["revenue_total"]
        revenue = clean.get("revenue")
        cogs = clean.get("cogs")
        if revenue is not None and cogs is not None:
            clean["gross_profit"] = revenue - cogs
        if clean.get("operating_profit") is not None:
            clean["ebit"] = clean["operating_profit"] + (clean.get("finance_expense") or 0.0)
        clean["da"] = sum(v for v in (clean.get("dep_fixed"), clean.get("dep_use_right"),
                                      clean.get("amort_intangible"), clean.get("amort_lt_prepaid"))
                          if v is not None) or clean.get("da_total")
        clean["total_debt"] = sum(v for v in (clean.get("short_debt"), clean.get("long_debt"),
                                              clean.get("bond"), clean.get("current_portion"))
                                  if v is not None) or None
        if clean.get("total_equity") is None and clean.get("total_equity_parent") is not None:
            clean["total_equity"] = clean["total_equity_parent"] + (clean.get("minority") or 0.0)
        # 单位一致性兜底：银行报表常以「百万元」列示，个别附注页会漏掉单位。
        # 股权/股本相对总资产小 3 个数量级时，按百万元补回。
        ta = clean.get("total_assets")
        if ta and clean.get("total_equity") and clean["total_equity"] < ta * 0.001:
            clean["total_equity"] *= 1e6
        if ta and clean.get("minority") and clean["minority"] < ta * 1e-6:
            clean["minority"] *= 1e6
        if clean.get("shares") and clean["shares"] < 1e7:
            clean["shares"] *= 1e6
        years_data[year] = clean

    return {
        "ok": bool(any(years_data.values()) or uniq_segments),
        "pdf": str(pdf_path),
        "report_year": report_year,
        "unit_scale": 1.0,
        "years": years_data,
        "segments": uniq_segments,
        "segment_pages": sorted(set(segment_pages)),
        "text_chars": len("".join(all_text)),
    }


# ======================================================================
# 五、组装成引擎输入
# ======================================================================


def _merge_year_data(all_years: dict[int, dict]) -> dict:
    # 缓存 JSON 的 key 会变成字符串，这里统一回整数
    all_years = {int(k): v for k, v in (all_years or {}).items() if str(k).isdigit()}
    years = sorted(all_years)
    if not years:
        return {}
    fields = ["revenue", "cogs", "gross_profit", "ebit", "operating_profit", "pretax_income",
              "tax_provision", "net_income", "net_income_parent", "finance_expense",
              "interest_expense", "eps", "da", "capex", "cfo", "dividends_paid",
              "receivables", "inventory", "payables"]
    out = {"years": years}
    for f in fields:
        out[f] = [all_years[y].get(f) for y in years]
    # 营运资本变动 = （应收+存货-应付）的同比变化；正数=占用增加
    nwc = []
    for y in years:
        d = all_years[y]
        if any(d.get(k) is not None for k in ("receivables", "inventory", "payables")):
            nwc.append((d.get("receivables") or 0.0) + (d.get("inventory") or 0.0)
                       - (d.get("payables") or 0.0))
        else:
            nwc.append(None)
    out["delta_nwc"] = [None] + [
        (nwc[i] - nwc[i - 1]) if (nwc[i] is not None and nwc[i - 1] is not None) else None
        for i in range(1, len(nwc))
    ]
    # 资产负债表用最新一年
    latest = all_years[years[-1]]
    for f in ["cash", "total_debt", "minority", "total_equity", "total_assets", "shares"]:
        out[f] = latest.get(f)
    out["minority_interest"] = latest.get("minority")
    out["preferred_stock"] = 0.0
    return out


def gather_company(company_name: str, ticker: str = "", years: list[int] | None = None,
                   max_reports: int = 3) -> dict:
    """搜索并解析最近 N 份年报，返回引擎可用的 financials / segments。"""
    today = date.today()
    latest_year = (years[-1] if years else today.year - 1)
    report_years = [latest_year - i for i in range(max_reports)]
    all_years: dict[int, dict] = {}
    all_segments = []
    sources = []
    reports = []
    warnings = []

    for year in report_years:
        key = f"annual_{ticker or company_name}_{year}"
        cached = cache.get(key, ttl_seconds=7 * 24 * 3600)
        if cached:
            parsed = cached
        else:
            found = find_annual_report(company_name, year, ticker)
            if not found.get("ok"):
                warnings.append(found.get("error") or f"{year} 年报未找到")
                continue
            try:
                pdf_path = download_pdf(found["url"], f"{ticker or 'company'}_{year}")
                parsed = parse_annual_report(pdf_path, year)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{year} 年报下载/解析失败：{type(exc).__name__}: {str(exc)[:100]}")
                continue
            parsed["url"] = found["url"]
            parsed["title"] = found.get("title", "")
            cache.put(key, parsed)
        reports.append(parsed)
        sources.append(source(f"年报 PDF·{year}", "财务报表/分部", as_of=f"{year}-12-31",
                              official=True, note=parsed.get("url", "")))
        for y, vals in (parsed.get("years") or {}).items():
            if y not in all_years:
                all_years[y] = vals
        if not all_segments and parsed.get("segments"):
            all_segments = parsed["segments"]

    if not all_years:
        return {"ok": False, "error": "未能从年报 PDF 抽取到财务数据",
                "warnings": warnings, "sources": sources, "reports": reports}

    financials = _merge_year_data(all_years)
    return {
        "ok": True,
        "financials": financials,
        "segments": all_segments,
        "sources": sources,
        "reports": reports,
        "warnings": warnings,
        "method": "web_search+annual_report_pdf",
        "as_of": f"{max(all_years)}-12-31",
    }


def fetch_company(ticker: str, market: str = "A", name: str = "",
                  years: list[int] | None = None) -> dict:
    """给数据层的统一入口。name 为空时先用行情/公司信息补。"""
    if market != "A":
        return {"ok": False, "error": "联网年报解析当前只支持 A 股。"}
    if not name:
        try:
            from . import akshare_provider as ak
            info = ak.company_info(ticker)
            name = info.get("name") or ticker
        except Exception:  # noqa: BLE001
            name = ticker
    result = gather_company(name, ticker, years=years)
    result["name"] = name
    result["ticker"] = ticker
    return result
