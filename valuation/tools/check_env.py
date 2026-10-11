"""检查数据/Excel 依赖在哪些解释器里可用。

    py valuation/tools/check_env.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CANDIDATES = [
    ("iFinD 自带运行时",
     r"D:\大二\iFinD\FinWork\resources\skill-python\runtime\win32-x64\python\python.exe"),
    ("用户 py（当前）", sys.executable),
]

PROBE = (
    "import importlib\n"
    "for m in ('akshare','yfinance','pandas','numpy','openpyxl'):\n"
    "    try:\n"
    "        mod = importlib.import_module(m)\n"
    "        v = getattr(mod, '__version__', '?')\n"
    "        print('  %-10s %s' % (m, v))\n"
    "    except Exception:\n"
    "        print('  %-10s 缺' % m)\n"
)


def main() -> int:
    for label, path in CANDIDATES:
        print(f"=== {label} ===")
        print(f"    {path}")
        if not Path(path).exists():
            print("    （不存在）\n")
            continue
        try:
            proc = subprocess.run([path, "-c", PROBE], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=180)
            print(proc.stdout or proc.stderr[-600:])
        except Exception as exc:  # noqa: BLE001
            print(f"    失败: {exc}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
