"""冒烟测试：估值引擎能跑出完整结果。

    py valuation/tools/smoke_engine.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import run  # noqa: E402


def sample_input() -> dict:
    """贵州茅台，用真实量级的演示数据（单位：元）。"""
    return {
        "company": {
            "name": "贵州茅台", "ticker": "600519", "market": "A", "currency": "CNY",
            "industry": "白酒", "report_period": "2025-12-31", "price_date": "2026-10-09",
        },
        "financials": {
            "years": [2021, 2022, 2023, 2024, 2025],
            "revenue": [109464278564, 127553959356, 150560330316, 174144069958, 172054171891],
            "cogs": [8983377810, 10093468617, 11867273852, 13789482368, 14892277571],
            "ebit": [74500000000, 87800000000, 103200000000, 119700000000, 114808950164],
            "pretax_income": [74700000000, 88000000000, 103600000000, 120100000000, 115000000000],
            "tax_provision": [18807501938, 22325449790, 26141077412, 30303850169, 29444936771],
            "net_income": [55720529956, 65376039958, 77521476278, 89334728026, 85310324834],
            "interest_expense": [0, 0, 0, 0, 0],
            "da": [1500000000, 1700000000, 1900000000, 2000000000, 2100000000],
            "capex": [3408784532, 5306546417, 2619755889, 4678712054, 3127594916],
            "delta_nwc": [2000000000, 2500000000, 2800000000, 3000000000, 2900000000],
            "total_debt": 500000000,
            "cash": 51690610947,
            "minority_interest": 0,
            "preferred_stock": 0,
            "total_assets": 303834840000,
            "total_equity": 253959253909,
            "price": 1263.0,
            "shares_outstanding": 1252270215,
            "market_cap": 1581617281455,
            "beta": 0.8153,
        },
        "peers": [
            {"name": "五粮液", "ticker": "000858", "pe": 8.25, "ps": 3.07, "pb": 2.01,
             "ev_ebitda": 5.6, "revenue_growth": 0.05, "ebitda_margin": 0.42},
            {"name": "泸州老窖", "ticker": "000568", "pe": 9.69, "ps": 4.09, "pb": 2.11,
             "ev_ebitda": 6.2, "revenue_growth": 0.08, "ebitda_margin": 0.45},
            {"name": "山西汾酒", "ticker": "600809", "pe": 11.48, "ps": 3.65, "pb": 3.52,
             "ev_ebitda": 7.1, "revenue_growth": 0.12, "ebitda_margin": 0.38},
            {"name": "洋河股份", "ticker": "002304", "pe": 8.42, "ps": 1.94, "pb": 1.09,
             "ev_ebitda": 5.1, "revenue_growth": -0.05, "ebitda_margin": 0.30},
            {"name": "古井贡酒", "ticker": "000596", "pe": 13.45, "ps": 2.60, "pb": 1.88,
             "ev_ebitda": 8.3, "revenue_growth": 0.10, "ebitda_margin": 0.31},
        ],
        "assumptions": {
            "forecast_years": 5,
            "terminal_growth": 0.03,
            "erp": 0.0514,
            "risk_free": 0.016864,
        },
        "relative_multiples": ["pe", "ps", "pb", "ev_ebitda"],
        "sources": [
            {"name": "新浪财经·财务报表", "as_of": "2026-10-10", "official": False},
            {"name": "中国债券信息网·10年期国债", "as_of": "2026-10-09", "official": True},
        ],
    }


def main() -> int:
    result = run(sample_input())

    print(f"标的：{result['company']['name']}（{result['company']['ticker']}）")
    print(f"市价：{result['dcf'].get('wacc_block', {}).get('beta', '—')} 倍 Beta  "
          f"→ WACC {result['dcf'].get('wacc', 0):.2%}\n")

    dcf = result["dcf"]
    if dcf.get("ok"):
        print("=== DCF ===")
        print(f"  首年增速 {dcf['revenue_growth_y1']:.2%}（{dcf['revenue_growth_y1_source']}）"
              f" → 永续 {dcf['terminal_growth']:.2%}")
        print(f"  EBIT 利润率 {dcf['ebit_margin']:.2%}（{dcf['ebit_margin_source']}）")
        print(f"  终值：Gordon {dcf['tv_gordon'] / 1e8:,.0f} 亿 | "
              f"退出倍数 {dcf['tv_exit'] / 1e8:,.0f} 亿 | 取中点 {dcf['tv_base'] / 1e8:,.0f} 亿")
        print(f"  企业价值 {dcf['enterprise_value'] / 1e8:,.0f} 亿  "
              f"→ 股权价值 {dcf['equity_value'] / 1e8:,.0f} 亿  "
              f"→ 每股 {dcf['per_share']:,.2f} 元")
        print(f"  终值占比 {dcf['tv_ratio']:.1%}")
    else:
        print("DCF 失败:", dcf.get("error"))

    rel = result["relative"]
    if rel.get("ok"):
        print(f"\n=== 相对估值（{rel['peers_used']} 家可比）===")
        for r in rel["results"]:
            print(f"  {r['label']:<16} 同业中位 {r['peer_median']:>8.2f} × "
                  f"{r['metric_basis']} → 每股 {r['implied_per_share']:>10,.2f} 元")
        print(f"  中位结论：每股 {rel['implied_per_share']:,.2f} 元  "
              f"（区间 {rel['range_low'] / 1e8:,.0f} ~ {rel['range_high'] / 1e8:,.0f} 亿）")

    b = result["blended"]
    if b.get("ok"):
        print(f"\n=== 三法融合 ===")
        print(f"  {b['weight_source']}")
        for c in b["components"]:
            print(f"  {c['label']:<18} 权重 {c['weight']:.0%}  每股 {c['per_share']:,.2f} 元")
        print(f"  → 融合每股 {b['blended_per_share']:,.2f} 元，"
              f"现价 {b['current_price']:,.2f} 元，"
              f"{b['verdict']} {b['upside']:+.1%}")

    sc = result.get("scenarios") or {}
    if sc:
        print(f"\n=== 三情景 ===")
        for key in ("bull", "base", "bear"):
            s = sc[key]
            print(f"  {s['label']}：每股 {s['per_share']:,.2f} 元  "
                  f"（增速 {s['growth_y1']:.1%} / 利润率 {s['ebit_margin']:.1%} / "
                  f"WACC {s['wacc']:.2%}）")

    sens = result.get("sensitivity") or {}
    if sens.get("grid"):
        print(f"\n=== 敏感性（每股，行=WACC 列=g）===")
        print("         " + "".join(f"{g:>11.2%}" for g in sens["growth_axis"]))
        for w, row in zip(sens["wacc_axis"], sens["grid"]):
            cells = "".join(f"{v:>11,.2f}" if v else f"{'—':>11}" for v in row)
            print(f"  {w:>6.2%}{cells}")

    if result["warnings"]:
        print("\n=== 提示 ===")
        for w in result["warnings"][:8]:
            print(f"  ⚠ {w}")

    out = Path(__file__).resolve().parent.parent / "demo" / "output_sample.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完整结果已写到 {out}")

    # 渲染 Excel 底稿
    from engine import excel
    xlsx = Path(__file__).resolve().parent.parent / "demo" / "valuation_model.xlsx"
    excel.render(result, xlsx)
    print(f"Excel 底稿已写到 {xlsx}  ({xlsx.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
