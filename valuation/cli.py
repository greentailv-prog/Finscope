"""FinScope 估值模块 · 命令行入口。

    py valuation/cli.py value 600519              # A 股，自动取数 → 估值 → 出 Excel
    py valuation/cli.py value AAPL --market US    # 美股
    py valuation/cli.py value 600519 --out 茅台估值.xlsx
    py valuation/cli.py run demo/input_sample.json   # 用现成的输入 JSON 跑
    py valuation/cli.py health                    # 数据层自检

输出：
    <工作目录>/output/<标的>_valuation.json    统一结果 JSON（D 的总集成读这个）
    <工作目录>/output/<标的>_valuation.xlsx    Excel 底稿
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from datasource import fetch as ds_fetch  # noqa: E402
from datasource import health as ds_health  # noqa: E402
from engine import excel, run  # noqa: E402

OUT_DIR = ROOT / "output"


def _build_input(ticker: str, market: str) -> tuple[dict, list[str]]:
    """取数 → 组装成引擎输入。返回 (payload, warnings)。"""
    warnings: list[str] = []
    data = ds_fetch(ticker, market)

    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "取数失败")

    warnings.extend(data.get("warnings") or [])
    fin = data.get("financials") or {}

    return {
        "company": {
            "name": data.get("name") or ticker,
            "ticker": data.get("code") or ticker,
            "market": data.get("market") or market,
            "currency": data.get("currency") or ("CNY" if market == "A" else "USD"),
            "industry": data.get("industry", ""),
            "sector": data.get("sector", ""),
            "report_period": f"{fin.get('years', [None])[-1]}-12-31" if fin.get("years") else "",
        },
        "financials": fin,
        "peers": [],                 # 可比公司需另外提供（见 README 的说明）
        "assumptions": {},           # 用引擎默认值；市场参数按 A/US 自动取
        "relative_multiples": ["pe", "ps", "pb"],
        "sources": data.get("sources") or [],
        "meta": {"data_source": data.get("source", "akshare/yfinance")},
    }, warnings


def cmd_value(args) -> int:
    market = args.market or ("A" if str(args.ticker).isdigit() else "US")
    print(f"取数：{args.ticker}（{market}）…")
    payload, warnings = _build_input(args.ticker, market)

    if args.peers:
        peers_path = Path(args.peers)
        if peers_path.exists():
            payload["peers"] = json.loads(peers_path.read_text(encoding="utf-8"))
            print(f"  可比公司：{len(payload['peers'])} 家（{peers_path.name}）")
        else:
            print(f"  ⚠ 找不到可比公司文件 {peers_path}，相对估值将跳过")
    else:
        print("  ⚠ 未提供可比公司（--peers），相对估值将跳过")

    print("估值计算…")
    result = run(payload)
    result["warnings"] = list(result.get("warnings") or []) + warnings

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = args.out.stem if args.out else f"{payload['company']['ticker']}_valuation"
    json_path = OUT_DIR / f"{stem}.json"
    xlsx_path = OUT_DIR / f"{stem}.xlsx"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    excel.render(result, xlsx_path)

    _print_summary(result)
    print(f"\n结果 JSON   {json_path}")
    print(f"Excel 底稿  {xlsx_path}")
    return 0


def cmd_run(args) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = run(payload)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(args.input).stem.replace("input_", "")
    json_path = OUT_DIR / f"{stem}_output.json"
    xlsx_path = OUT_DIR / f"{stem}.xlsx"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    excel.render(result, xlsx_path)
    _print_summary(result)
    print(f"\n结果 JSON   {json_path}")
    print(f"Excel 底稿  {xlsx_path}")
    return 0


def cmd_health(_args) -> int:
    info = ds_health()
    print("数据层自检")
    print(f"  Python        {info.get('data_python')}  ({info.get('data_python_label')})")
    print(f"  可用模块      {info.get('usable_module')}")
    print(f"  akshare       {info.get('akshare') or '缺'}")
    print(f"  yfinance      {info.get('yfinance') or '缺'}")
    print(f"  pandas        {info.get('pandas') or '缺'}")
    print(f"  openpyxl      {info.get('openpyxl') or '缺'}")
    print(f"  iFinD 接口    {'已就绪' if info.get('ifind') else '未接入'}")
    print(f"  Choice 接口   {'已就绪' if info.get('choice') else '未接入'}")
    print(f"  数据源优先级  {' > '.join(info.get('source_priority') or [])}")
    if not info.get("ok"):
        print(f"  ⚠ {info.get('reason')}")
    return 0


def _print_summary(result: dict) -> None:
    company = result.get("company") or {}
    blended = result.get("blended") or {}
    dcf = result.get("dcf") or {}
    rel = result.get("relative") or {}

    print()
    print("=" * 64)
    print(f"{company.get('name')}（{company.get('ticker')}）")
    print("=" * 64)
    if dcf.get("ok"):
        print(f"  DCF        每股 {dcf['per_share']:,.2f}  （WACC {dcf['wacc']:.2%}，"
              f"g {dcf['terminal_growth']:.2%}）")
    if rel.get("ok"):
        print(f"  相对估值   每股 {rel['implied_per_share']:,.2f}  "
              f"（{rel.get('peers_used', 0)} 家可比）")
    if blended.get("ok"):
        print(f"  融合        每股 {blended['blended_per_share']:,.2f}  "
              f"现价 {blended.get('current_price')}  →  {blended.get('verdict')} "
              f"{blended.get('upside'):+.1%}" if blended.get("upside") is not None
              else f"  融合        每股 {blended['blended_per_share']:,.2f}")

    warns = result.get("warnings") or []
    if warns:
        print(f"\n  提示 {len(warns)} 条：")
        for w in warns[:5]:
            print(f"    ⚠ {str(w)[:110]}")
        if len(warns) > 5:
            print(f"    …还有 {len(warns) - 5} 条，见结果 JSON")


def main() -> int:
    parser = argparse.ArgumentParser(description="FinScope 估值模块")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("value", help="取数并估值，输出 JSON + Excel")
    p_val.add_argument("ticker", help="股票代码，如 600519 / AAPL")
    p_val.add_argument("--market", choices=["A", "US"], help="留空自动判断")
    p_val.add_argument("--peers", help="可比公司 JSON 文件路径")
    p_val.add_argument("--out", type=Path, help="输出文件名（可省）")
    p_val.set_defaults(func=cmd_value)

    p_run = sub.add_parser("run", help="用现成的输入 JSON 跑估值")
    p_run.add_argument("input", help="输入 JSON 路径")
    p_run.set_defaults(func=cmd_run)

    p_h = sub.add_parser("health", help="数据层自检")
    p_h.set_defaults(func=cmd_health)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"\n✘ {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
