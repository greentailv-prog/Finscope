"""把 tests/reports(_web) 里的年报/公开财报快照转成 ABC canonical 输入。

只用于离线回归和交付样例生成；正式运行由 D 的 to_c_input 或
/api/valuation/from-workflow 传入同等结构的财务记录。
"""
from __future__ import annotations

import json
from pathlib import Path

VALUATION = Path(__file__).resolve().parents[1]
REPORTS = VALUATION / "tests" / "reports"
REPORTS_WEB = VALUATION / "tests" / "reports_web"


def _records_from_series(fin: dict, source: str, source_type: str = "pdf",
                         skip: tuple[str, ...] = ()) -> dict:
    years = fin.get("years") or []
    out: dict[str, dict] = {}
    for key, val in fin.items():
        if key == "years" or key in skip:
            continue
        if isinstance(val, list):
            series = {str(y): v for y, v in zip(years, val) if isinstance(v, (int, float))}
            if not series:
                continue
            last = series.get(str(years[-1]), list(series.values())[-1])
            out[key] = {"value": last, "series": series, "period": str(years[-1]),
                        "status": "found", "unit": "元", "scope": "合并报表",
                        "source_id": "S01", "source_type": source_type, "source": source}
        elif isinstance(val, (int, float)):
            out[key] = {"value": val, "series": {str(years[-1]): val}, "period": str(years[-1]),
                        "status": "found", "unit": "元", "scope": "合并报表",
                        "source_id": "S01", "source_type": source_type, "source": source}
    return out


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def maotai_payload(price: float | None = 1480.0) -> dict:
    """600519：优先使用年报 PDF 抽取（web_evidence），符合「用户资料优先」。"""
    ev = _read(REPORTS_WEB / "600519_web_evidence.json")
    fin = ev["financials"]
    # 该 PDF 抽取器的存货字段为负值，疑似口径错误；按缺失处理，不写成事实。
    records = _records_from_series(fin, "600519 2025 年报 PDF", skip=("inventory",))
    last_year = str(fin["years"][-1])
    for key in ("cash", "total_debt"):
        records["cash_and_equivalents" if key == "cash" else key] = {
            "value": fin[key], "series": {last_year: fin[key]}, "period": last_year,
            "status": "found", "unit": "元", "scope": "合并报表",
            "source_id": "S01", "source_type": "pdf", "source": "600519 2025 年报 PDF",
        }
    ref = _read(REPORTS_WEB / "600519_result.json")
    shares = fin.get("shares")
    return {
        "schema_version": "2.0",
        "meta": {"source_mode": "upload", "period_type": "annual", "currency": "CNY"},
        "company": {"name": "贵州茅台", "ticker": "600519", "market": "A",
                    "currency": "CNY", "industry": "白酒Ⅱ",
                    "report_period": f"{last_year}-12-31"},
        "financials": records,
        "market_data": {"price": price, "shares_outstanding": shares,
                        "market_cap": (price * shares if price else None),
                        "price_date": "2026-11-03", "price_time": "",
                        "price_source": "东方财富公司信息"},
        "peers": ref["peer_selection"]["peers"],
        "sources": ev.get("sources") or [],
        "method_selection": "auto",
        "fetch_data": False,
        "data_source": "canonical",
        "data_quality": {"blocked": False, "checks": [], "review_queue": []},
    }


def bank_payload() -> dict:
    """600036：银行口径，验证 DDM/剩余收益 + PB/PE Comps 的 status 语义。"""
    ref = _read(REPORTS / "600036_result.json")
    hist = ref["history"]
    records = _records_from_series(hist, "招商银行 2025 年报 / 公开财报", source_type="online")
    records["total_equity"] = {
        "value": 1280899000000.0, "series": {"2025": 1280899000000.0}, "period": "2025",
        "status": "found", "unit": "元", "scope": "合并报表", "source_id": "S02",
        "source_type": "online", "source": "招商银行 2025 年报",
    }
    return {
        "schema_version": "2.0",
        "meta": {"source_mode": "online", "period_type": "annual", "currency": "CNY"},
        "company": {"name": "招商银行", "ticker": "600036", "market": "A",
                    "currency": "CNY", "industry": "银行Ⅱ",
                    "report_period": "2025-12-31"},
        "financials": records,
        "market_data": ref["market_data"],
        "peers": ref["peer_selection"]["peers"],
        "sources": [{"source_id": "S02", "source": "招商银行 2025 年报",
                     "source_type": "online", "source_url": "", "page": None,
                     "as_of": "2025-12-31"}],
        "assumptions": {"dividend_payout": ref["ddm"]["payout_ratio"]},
        "method_selection": "auto",
        "fetch_data": False,
        "data_source": "canonical",
        "data_quality": {"blocked": False, "checks": [], "review_queue": []},
    }


def history_payload(ticker: str, industry: str, name: str = "") -> dict:
    """000333/000858 等：用已保存的公开财报快照重建 canonical 输入。"""
    ref = _read(REPORTS / f"{ticker}_result.json")
    hist = ref["history"]
    records = _records_from_series(hist, f"{ticker} 公开财报快照", source_type="online")
    for key in ("cash", "debt"):
        value = (ref.get("dcf") or {}).get(key)
        if value is not None:
            records["cash_and_equivalents" if key == "cash" else "total_debt"] = {
                "value": value, "series": {str(hist["years"][-1]): value},
                "period": str(hist["years"][-1]), "status": "found", "unit": "元",
                "scope": "合并报表", "source_id": "S03", "source_type": "online",
                "source": f"{ticker} 公开财报快照",
            }
    return {
        "schema_version": "2.0",
        "meta": {"source_mode": "online", "period_type": "annual", "currency": "CNY"},
        "company": {"name": name or ref.get("company", {}).get("name") or ticker,
                    "ticker": ticker, "market": "A", "currency": "CNY",
                    "industry": industry,
                    "report_period": f"{hist['years'][-1]}-12-31"},
        "financials": records,
        "market_data": ref.get("market_data") or {},
        "peers": (ref.get("peer_selection") or {}).get("peers") or [],
        "sources": [{"source_id": "S03", "source": f"{ticker} 公开财报快照",
                     "source_type": "online", "source_url": "", "page": None,
                     "as_of": f"{hist['years'][-1]}-12-31"}],
        "method_selection": "auto",
        "fetch_data": False,
        "data_source": "canonical",
        "data_quality": {"blocked": False, "checks": [], "review_queue": []},
    }
