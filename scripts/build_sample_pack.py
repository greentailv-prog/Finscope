"""按年报/公开财报快照动态生成四家样例的结果 JSON、18 表底稿和前端样例。

这不是静态数据入口：每次运行都会重新调用估值引擎、重新生成 Excel，
并覆盖 valuation/output/ 下的同名文件。正式分析任意 A 股请用
`python -m valuation.cli value <代码>` 或 D 的 /api/valuation/from-workflow。

用法（仓库根目录）：
    python -m valuation.scripts.build_sample_pack
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from valuation import run  # noqa: E402
from valuation.tests.sample_inputs import bank_payload, history_payload, maotai_payload  # noqa: E402

OUT = ROOT / "output"
FRONTEND = ROOT / "frontend" / "sample_data.js"

CASES = [
    ("600519", "贵州茅台", lambda: maotai_payload(1480.0)),
    ("000333", "美的集团", lambda: history_payload("000333", "家用电器", "美的集团")),
    ("000858", "五粮液", lambda: history_payload("000858", "白酒Ⅱ", "五粮液")),
    ("600036", "招商银行", bank_payload),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    samples = {}
    for ticker, name, make in CASES:
        result = run(make(), fetch=False, export_excel=True)
        year = ((result.get("company") or {}).get("report_period") or "")[:4] \
            or str(result.get("as_of") or "latest")
        json_path = OUT / f"{ticker}_{year}_result.json"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        samples[ticker] = result
        print(f"{ticker} {name}: status={result.get('status')} "
              f"support={result.get('industry_support')} "
              f"dcf={((result.get('dcf') or {}).get('per_share'))} "
              f"excel={result.get('excel_path')} ({result.get('excel_format')})")
    FRONTEND.write_text(
        "window.SAMPLES = " + json.dumps(samples, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    print(f"written {FRONTEND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
