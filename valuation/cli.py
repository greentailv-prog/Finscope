"""FinScope 估值模块 v2 · 命令行入口。

    py cli.py value 600519                 # 自动取数 → 规则补假设 → 四法估值 → Excel
    py cli.py value 600519 --method dcf   # 只做绝对估值
    py cli.py value 600519 --method comps # 只做 Comps
    py cli.py value 000333 --method sotp  # 只做 SOTP
    py cli.py run input.json              # 用现成输入 JSON
    py cli.py questions 600519            # 看交互式对话框该问什么
    py cli.py health                      # 数据层自检
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from valuation import next_questions, run  # noqa: E402
from valuation.core import defaults  # noqa: E402
from valuation.data import official_provider as official  # noqa: E402
from valuation.data import web_provider as web  # noqa: E402

OUT_DIR = ROOT / "output"


def _payload(ticker: str, market: str, method: str, peers_file: str | None,
             assumptions: str | None, data_source: str = "auto") -> dict:
    payload = {
        "company": {
            "ticker": ticker,
            "market": market,
            "name": "",
            "currency": "CNY" if market == "A" else "USD",
        },
        "method_selection": method,
        "fetch_data": True,
        "data_source": data_source,
    }
    if peers_file:
        payload["peers"] = json.loads(Path(peers_file).read_text(encoding="utf-8"))
    if assumptions:
        payload["assumptions"] = json.loads(Path(assumptions).read_text(encoding="utf-8"))
    return payload


def cmd_value(args) -> int:
    market = args.market or ("A" if str(args.ticker).isdigit() else "US")
    print(f"取数并估值：{args.ticker}（{market}，方法={args.method}）…")
    payload = _payload(args.ticker, market, args.method, args.peers, args.assumptions,
                       data_source=args.source)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = args.out or f"{args.ticker}_valuation_v2"
    json_path = OUT_DIR / f"{stem}.json"
    xlsx_path = OUT_DIR / f"{stem}.xlsx"
    result = run(payload, export_excel=True, excel_path=str(xlsx_path))
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str),
                         encoding="utf-8")
    _print_summary(result)
    print(f"\n结果 JSON   {json_path}")
    if result.get("excel_path"):
        print(f"Excel 底稿  {result['excel_path']}")
    return 0


def cmd_run(args) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(args.input).stem.replace("input_", "")
    json_path = OUT_DIR / f"{stem}_output_v2.json"
    xlsx_path = OUT_DIR / f"{stem}_v2.xlsx"
    result = run(payload, export_excel=True, excel_path=str(xlsx_path))
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str),
                         encoding="utf-8")
    _print_summary(result)
    print(f"\n结果 JSON   {json_path}")
    print(f"Excel 底稿  {xlsx_path}")
    return 0


def cmd_questions(args) -> int:
    market = args.market or ("A" if str(args.ticker).isdigit() else "US")
    info = next_questions({"company": {"ticker": args.ticker, "market": market}})
    print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_search(args) -> int:
    """联网搜索 + 年报 PDF 解析，输出证据包。"""
    years = None
    if args.years:
        try:
            start, end = [int(x) for x in args.years.split("-")]
            years = list(range(start, end + 1))
        except ValueError:
            print("--years 格式应为 2022-2025", file=sys.stderr)
            return 2
    name = args.name or ""
    if not name:
        from valuation.data import akshare_provider as ak
        info = ak.company_info(args.ticker)
        name = info.get("name") or args.ticker
    result = web.gather_company(name, args.ticker, years=years, max_reports=args.reports)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{args.ticker}_web_evidence.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str),
                    encoding="utf-8")
    print(f"公司：{name}（{args.ticker}）")
    print(f"结果：{'成功' if result.get('ok') else '失败'}")
    for w in result.get("warnings") or []:
        print("  ⚠", w)
    f = result.get("financials") or {}
    if f.get("years"):
        print(f"  年度：{f['years']}")
        print(f"  营收（亿元）：{[round(x / 1e8, 1) if x else None for x in f.get('revenue', [])]}")
        print(f"  净利（亿元）：{[round(x / 1e8, 1) if x else None for x in f.get('net_income', [])]}")
    if result.get("segments"):
        print("  分部：", ", ".join(f"{s['name']} {s['revenue'] / 1e8:.1f}亿"
                                  for s in result["segments"][:8]))
    print(f"证据包：{path}")
    return 0 if result.get("ok") else 1


def cmd_probe_sources(_args) -> int:
    print(json.dumps(official.probe_all(), ensure_ascii=False, indent=2))
    return 0


def cmd_health(_args) -> int:
    import importlib
    print("数据层自检")
    for mod in ("akshare", "pandas", "numpy", "openpyxl", "fastapi"):
        try:
            m = importlib.import_module(mod)
            print(f"  {mod:<10} {getattr(m, '__version__', 'installed')}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {mod:<10} 缺（{type(exc).__name__}）")
    print(f"  配置         {defaults.CONFIG_DIR}")
    print(f"  行业池       {len(defaults.industry_peers().get('themes', {}))} 个主题")
    return 0


def _print_summary(result: dict) -> None:
    company = result.get("company") or {}
    print()
    print("=" * 68)
    print(f"{company.get('name') or company.get('ticker')}（{company.get('ticker')}）  "
          f"状态={result.get('status')}  行业支持={result.get('industry_support')}")
    print("=" * 68)
    plan = result.get("method_plan") or {}
    print(f"  方法：{plan.get('reason')}")
    for key, label in (("dcf", "DCF"), ("comps", "Comps"), ("sotp", "SOTP"), ("ddm", "DDM")):
        block = result.get(key) or {}
        if block.get("ok"):
            ps = block.get("per_share") if key != "comps" else block.get("implied_per_share")
            rel = (result.get("reliabilities") or {}).get(key, {})
            print(f"  {label:<6} 每股 {ps:,.2f}  可靠性 {rel.get('score')}（{rel.get('level')}）"
                  if ps is not None else f"  {label:<6} 已计算（无每股价值）")
    blended = result.get("blended") or {}
    if blended.get("ok"):
        weights = blended.get("weights") or {}
        print(f"  权重：{' / '.join(f'{k} {v:.0%}' for k, v in weights.items())}")
        print(f"  融合  每股 {blended.get('blended_per_share'):,.2f}  "
              f"现价 {blended.get('current_price')}  →  {blended.get('verdict')} "
              f"{blended.get('upside'):+.1%}  置信度 {blended.get('confidence')}")
    warns = result.get("warnings") or []
    if warns:
        print(f"\n  提示 {len(warns)} 条：")
        for w in warns[:8]:
            print(f"    ⚠ {str(w)[:120]}")
        if len(warns) > 8:
            print(f"    …还有 {len(warns) - 8} 条，见 JSON")


def main() -> int:
    parser = argparse.ArgumentParser(description="FinScope 估值模块 v2")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("value", help="取数并估值")
    p_val.add_argument("ticker")
    p_val.add_argument("--market", choices=["A", "US"])
    p_val.add_argument("--method", default="auto",
                       choices=["auto", "blended", "dcf", "comps", "sotp", "ddm",
                                "dcf+comps", "dcf+sotp", "comps+sotp"])
    p_val.add_argument("--peers", help="可比公司 JSON 文件")
    p_val.add_argument("--assumptions", help="假设 JSON 文件")
    p_val.add_argument("--out", help="输出文件名（不含扩展名）")
    p_val.add_argument("--source", default="auto",
                       choices=["auto", "ifind", "choice", "web", "akshare"],
                       help="数据源：auto=官方源→akshare；web=联网年报 PDF")
    p_val.set_defaults(func=cmd_value)

    p_run = sub.add_parser("run", help="用输入 JSON 跑")
    p_run.add_argument("input")
    p_run.set_defaults(func=cmd_run)

    p_q = sub.add_parser("questions", help="交互式对话框问题清单")
    p_q.add_argument("ticker")
    p_q.add_argument("--market", choices=["A", "US"])
    p_q.set_defaults(func=cmd_questions)

    p_s = sub.add_parser("search", help="联网搜索 + 年报 PDF 解析（输出证据包）")
    p_s.add_argument("ticker")
    p_s.add_argument("--name", help="公司名称（不填则自动查）")
    p_s.add_argument("--years", help="如 2022-2025")
    p_s.add_argument("--reports", type=int, default=3, help="下载最近几份年报，默认 3")
    p_s.set_defaults(func=cmd_search)

    p_probe = sub.add_parser("probe-sources", help="探测 iFinD / Choice 是否可用")
    p_probe.set_defaults(func=cmd_probe_sources)

    p_h = sub.add_parser("health", help="数据层自检")
    p_h.set_defaults(func=cmd_health)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"\n✘ {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
