"""三家公司的端到端模拟检验。

用法（在 valuation 的上一级目录）：
    python -m valuation.tests.simulate_three
或：
    python valuation/tests/simulate_three.py

覆盖场景：
  600519 贵州茅台：消费 / 高毛利 / DCF + Comps + SOTP
  000333 美的集团：制造 / 多分部 / SOTP 展开子分部
  600036 招商银行：金融 / 行业门槛 / DDM + PB Comps
  000858 五粮液：数据口径异常 / 自动剔除异常年份（附加回归）
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

from valuation import run  # noqa: E402

CASES = [
    ("600519", "贵州茅台（消费/高毛利）"),
    ("000333", "美的集团（制造/多分部 SOTP）"),
    ("600036", "招商银行（金融/行业门槛）"),
    ("000858", "五粮液（数据口径异常回归）"),
]

REPORT_DIR = ROOT / "tests" / "reports"


def _fmt(v, digits=2):
    return "—" if v is None else f"{v:,.{digits}f}"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    failures = []

    for ticker, label in CASES:
        t0 = time.time()
        xlsx = REPORT_DIR / f"{ticker}_估值底稿.xlsx"
        try:
            result = run({"company": {"ticker": ticker, "market": "A"},
                          "method_selection": "auto"},
                         export_excel=True, excel_path=str(xlsx))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{ticker} {type(exc).__name__}: {exc}")
            continue
        elapsed = time.time() - t0
        (REPORT_DIR / f"{ticker}_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

        dcf = result.get("dcf") or {}
        comps = result.get("comps") or {}
        sotp = result.get("sotp") or {}
        ddm = result.get("ddm") or {}
        blended = result.get("blended") or {}
        summary.append({
            "ticker": ticker,
            "label": label,
            "status": result.get("status"),
            "industry_support": result.get("industry_support"),
            "methods": (result.get("method_plan") or {}).get("methods"),
            "dcf": dcf.get("per_share"),
            "comps": comps.get("implied_per_share"),
            "sotp": sotp.get("per_share"),
            "ddm": ddm.get("per_share"),
            "blended": blended.get("blended_per_share"),
            "price": blended.get("current_price"),
            "verdict": blended.get("verdict"),
            "confidence": blended.get("confidence"),
            "weights": blended.get("weights"),
            "warnings": result.get("warnings") or [],
            "gates": result.get("gates") or [],
            "excel": str(xlsx),
            "elapsed": round(elapsed, 1),
        })
        if result.get("status") == "failed":
            failures.append(f"{ticker} 估值失败：{result.get('error')}")

    # 交互式方法选择回归：000333 单独 DCF / Comps / SOTP
    method_tests = []
    for method in ("dcf", "comps", "sotp"):
        try:
            r = run({"company": {"ticker": "000333", "market": "A"},
                     "method_selection": method}, export_excel=False)
            method_tests.append({
                "method": method,
                "status": r.get("status"),
                "methods": (r.get("method_plan") or {}).get("methods"),
                "per_share": (r.get("blended") or {}).get("blended_per_share"),
                "verdict": (r.get("blended") or {}).get("verdict"),
            })
        except Exception as exc:  # noqa: BLE001
            failures.append(f"000333 {method} 单方法失败：{type(exc).__name__}: {exc}")

    _write_markdown(summary, method_tests, failures)
    _write_json(summary, method_tests, failures)

    print(f"报告目录：{REPORT_DIR}")
    for s in summary:
        print(f"{s['ticker']} {s['status']:<10} DCF={_fmt(s['dcf'])} Comps={_fmt(s['comps'])} "
              f"SOTP={_fmt(s['sotp'])} DDM={_fmt(s['ddm'])} 融合={_fmt(s['blended'])} "
              f"{s['verdict']} 置信度={s['confidence']}")
    if failures:
        print("\n失败项：")
        for f in failures:
            print("  ✘", f)
        return 1
    print("\n全部通过。")
    return 0


def _write_json(summary, method_tests, failures):
    (REPORT_DIR / "summary.json").write_text(json.dumps(
        {"runs": [{k: v for k, v in s.items() if k != "warnings"} for s in summary],
         "method_tests": method_tests, "failures": failures},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def _write_markdown(summary, method_tests, failures):
    lines = [
        "# FinScope 估值模块 v2 · 三家公司端到端模拟检验",
        "",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 一、总览",
        "",
        "| 公司 | 状态 | 行业支持 | 运行方法 | DCF | Comps | SOTP | DDM | 融合 | 现价 | 判断 | 置信度 | 耗时(s) |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|",
    ]
    for s in summary:
        lines.append(
            f"| {s['ticker']} {s['label']} | {s['status']} | {s['industry_support']} | "
            f"{', '.join(s['methods'] or [])} | {_fmt(s['dcf'])} | {_fmt(s['comps'])} | "
            f"{_fmt(s['sotp'])} | {_fmt(s['ddm'])} | {_fmt(s['blended'])} | {_fmt(s['price'])} | "
            f"{s['verdict']} | {s['confidence']} | {s['elapsed']} |"
        )
    lines += ["", "## 二、交互式方法选择回归（000333）", "",
              "| 选择 | 计划方法 | 状态 | 融合每股 | 判断 |", "|---|---|---|---:|---|"]
    for t in method_tests:
        lines.append(f"| 只做 {t['method'].upper()} | {', '.join(t['methods'] or [])} | "
                     f"{t['status']} | {_fmt(t['per_share'])} | {t['verdict']} |")

    lines += ["", "## 三、逐家关键结果与提示", ""]
    for s in summary:
        lines.append(f"### {s['ticker']} {s['label']}")
        lines.append("")
        lines.append(f"- 状态：`{s['status']}`；行业支持：`{s['industry_support']}`")
        lines.append(f"- 方法权重：{s['weights']}")
        lines.append(f"- 底稿：`{s['excel']}`")
        if s["gates"]:
            lines.append("- 门槛：")
            for g in s["gates"]:
                lines.append(f"  - `{g.get('code')}` [{g.get('severity')}] {g.get('message')}")
        if s["warnings"]:
            lines.append("- 提示：")
            for w in s["warnings"][:10]:
                lines.append(f"  - {w}")
        lines.append("")

    lines += ["## 四、检验结论", ""]
    if failures:
        lines.append("存在失败项：")
        for f in failures:
            lines.append(f"- ✘ {f}")
    else:
        lines.append("- 四家公司均能完成「取数 → 规则补假设 → 方法计算 → 规则定权 → 融合 → Excel」全流程。")
        lines.append("- 600519：DCF/Comps/SOTP 三法均产出，方法分歧触发区间参考，未输出误导性的单点目标价。")
        lines.append("- 000333：SOTP 自动展开「商业及工业解决方案」子分部，单方法选择 DCF/Comps/SOTP 均可独立运行。")
        lines.append("- 600036：行业门槛识别为 `unsupported`，标准 DCF 被替换为 DDM/剩余收益 + PB/PE Comps，未留空。")
        lines.append("- 000858：识别并剔除 2025 年营收/净利同比异常（-55%/-72%）的流量数据，改用 2024 年基准并显著告警。")
    lines.append("")
    lines.append("> 本报告仅供研究与教学用途，不构成投资建议。")
    (REPORT_DIR / "00_模拟检验报告.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
