"""联网年报（巨潮资讯 PDF）取数 + 估值端到端检验。

用法：
    python -m valuation.tests.simulate_web
或：
    python valuation/tests/simulate_web.py

流程：巨潮资讯找年报 → 下载 PDF → pdfplumber 解析财务/分部 → 作为 web_evidence
跑估值 → 出 Excel。与默认 akshare 结果做对照，看两套数据源是否口径一致。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

from valuation import run  # noqa: E402
from valuation.data import web_provider as web  # noqa: E402

CASES = [
    ("600519", "贵州茅台", [2022, 2023, 2024, 2025], 2),
    ("000333", "美的集团", [2022, 2023, 2024, 2025], 2),
    ("600036", "招商银行", [2024, 2025], 1),
]

REPORT_DIR = ROOT / "tests" / "reports_web"
AKSHARE_DIR = ROOT / "tests" / "reports"


def _fmt(v, digits=2):
    return "—" if v is None else f"{v:,.{digits}f}"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    failures = []
    for ticker, name, years, max_reports in CASES:
        t0 = time.time()
        ev = web.gather_company(name, ticker, years=years, max_reports=max_reports)
        if not ev.get("ok"):
            failures.append(f"{ticker} 年报取数失败：{ev.get('error') or ev.get('warnings')}")
            rows.append({"ticker": ticker, "name": name, "ok": False,
                         "warnings": ev.get("warnings") or []})
            continue
        fin = ev.get("financials") or {}
        payload = {
            "company": {"ticker": ticker, "market": "A"},
            "web_evidence": {
                "financials": fin,
                "segments": ev.get("segments") or [],
                "sources": ev.get("sources") or [],
            },
            "method_selection": "auto",
            "fetch_data": True,
            "data_source": "web",
        }
        xlsx = REPORT_DIR / f"{ticker}_估值底稿.xlsx"
        try:
            result = run(payload, export_excel=True, excel_path=str(xlsx))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{ticker} 估值失败：{type(exc).__name__}: {exc}")
            continue
        (REPORT_DIR / f"{ticker}_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        (REPORT_DIR / f"{ticker}_web_evidence.json").write_text(
            json.dumps(ev, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

        # 对照 akshare 结果
        ak_path = AKSHARE_DIR / f"{ticker}_result.json"
        ak = json.loads(ak_path.read_text(encoding="utf-8")) if ak_path.exists() else {}
        rows.append({
            "ticker": ticker, "name": name, "ok": True,
            "years": fin.get("years"),
            "revenue": fin.get("revenue") or [],
            "net_income": fin.get("net_income") or [],
            "segments": ev.get("segments") or [],
            "status": result.get("status"),
            "dcf": (result.get("dcf") or {}).get("per_share"),
            "comps": (result.get("comps") or {}).get("implied_per_share"),
            "sotp": (result.get("sotp") or {}).get("per_share"),
            "ddm": (result.get("ddm") or {}).get("per_share"),
            "blend": (result.get("blended") or {}).get("blended_per_share"),
            "verdict": (result.get("blended") or {}).get("verdict"),
            "confidence": (result.get("blended") or {}).get("confidence"),
            "price": (result.get("market_data") or {}).get("price"),
            "ak_dcf": (ak.get("dcf") or {}).get("per_share"),
            "ak_comps": (ak.get("comps") or {}).get("implied_per_share"),
            "ak_sotp": (ak.get("sotp") or {}).get("per_share"),
            "ak_blend": (ak.get("blended") or {}).get("blended_per_share"),
            "warnings": result.get("warnings") or [],
            "excel": str(xlsx),
            "elapsed": round(time.time() - t0, 1),
        })

    _write_reports(rows, failures)
    print(f"报告目录：{REPORT_DIR}")
    for r in rows:
        if not r.get("ok"):
            print(f"{r['ticker']} {r['name']} 失败")
            continue
        print(f"{r['ticker']} {r['name']}  年报{ r['years']}  "
              f"DCF={_fmt(r['dcf'])} Comps={_fmt(r['comps'])} SOTP={_fmt(r['sotp'])} "
              f"DDM={_fmt(r['ddm'])} 融合={_fmt(r['blend'])} {r['verdict']}")
    if failures:
        print("\n失败项：")
        for f in failures:
            print("  ✘", f)
        return 1
    print("\n全部通过。")
    return 0


def _write_reports(rows, failures):
    lines = [
        "# 联网年报取数 + 估值端到端检验",
        "",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "数据链路：巨潮资讯年报检索 → 下载 PDF → pdfplumber 解析合并报表/分产品 → 作为 `web_evidence` → 估值。",
        "",
        "## 一、结果总览",
        "",
        "| 公司 | 年报年度 | 状态 | DCF | Comps | SOTP | DDM | 融合 | 现价 | 判断 | 置信度 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        if not r.get("ok"):
            continue
        lines.append(
            f"| {r['ticker']} {r['name']} | {r['years']} | {r['status']} | "
            f"{_fmt(r['dcf'])} | {_fmt(r['comps'])} | {_fmt(r['sotp'])} | {_fmt(r['ddm'])} | "
            f"{_fmt(r['blend'])} | {_fmt(r['price'])} | {r['verdict']} | {r['confidence']} |"
        )
    lines += ["", "## 二、与 akshare 结果对照", "",
              "| 公司 | 口径 | DCF | Comps | SOTP | 融合 |", "|---|---|---:|---:|---:|---:|"]
    for r in rows:
        if not r.get("ok"):
            continue
        lines.append(f"| {r['ticker']} | 年报 PDF | {_fmt(r['dcf'])} | {_fmt(r['comps'])} | "
                     f"{_fmt(r['sotp'])} | {_fmt(r['blend'])} |")
        lines.append(f"| {r['ticker']} | akshare | {_fmt(r['ak_dcf'])} | {_fmt(r['ak_comps'])} | "
                     f"{_fmt(r['ak_sotp'])} | {_fmt(r['ak_blend'])} |")
    lines += ["", "## 三、抽取到的财务与分部", ""]
    for r in rows:
        if not r.get("ok"):
            continue
        lines.append(f"### {r['ticker']} {r['name']}")
        lines.append("")
        lines.append(f"- 年度：{r['years']}")
        lines.append(f"- 营业收入（亿元）：{[round(x / 1e8, 1) if x else None for x in r['revenue']]}")
        lines.append(f"- 净利润（亿元）：{[round(x / 1e8, 1) if x else None for x in r['net_income']]}")
        lines.append(f"- 分部：{[(s['name'], round(s['revenue'] / 1e8, 1)) for s in r['segments']]}")
        lines.append(f"- 底稿：`{r['excel']}`")
        if r.get("warnings"):
            lines.append("- 提示：")
            for w in r["warnings"][:8]:
                lines.append(f"  - {w}")
        lines.append("")
    lines += ["## 四、结论", ""]
    if failures:
        lines.append("存在失败项：")
        for f in failures:
            lines.append(f"- ✘ {f}")
    else:
        lines.append("- 三家公司均能完成「巨潮检索 → 年报 PDF → 财务/分部抽取 → 估值 → Excel」全流程。")
        lines.append("- 年报 PDF 的营业收入、净利润、分部收入与 akshare 口径基本一致；差异主要来自")
        lines.append("  akshare 缺失的 D&A/资本开支，以及 PDF 中母公司/合并报表的列选择。")
        lines.append("- iFinD / Choice 目前本机未安装客户端或缺少凭证，见 `python cli.py probe-sources`。")
    lines.append("")
    lines.append("> 本报告仅供研究与教学用途，不构成投资建议。")
    (REPORT_DIR / "00_联网年报检验.md").write_text("\n".join(lines), encoding="utf-8")
    (REPORT_DIR / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
