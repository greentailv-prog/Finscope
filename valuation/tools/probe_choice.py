"""Choice（东方财富）量化接口连通性自检。

装好接口、配好帐号后跑这个：

    py valuation/tools/probe_choice.py
    py valuation/tools/probe_choice.py 600519      # 顺带实测截面数据

**不会打印密码。**
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datasource import choice  # noqa: E402

# Choice 的截面指标名（候选，需实测）
CANDIDATES = [
    "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME",
    "PE", "PB", "PS", "PE_TTM",
    "TOTAL_ASSETS", "TOTAL_LIABILITIES", "TOTAL_EQUITY",
    "OPER_REV", "NET_PROFIT_EXCL_MIN_INT_INC", "TOTAL_OPER_INCOME",
    "NET_CASH_FLOWS_OPER_ACT",
]


def main() -> int:
    print("=" * 66)
    print("1. 环境检查")
    print("=" * 66)

    user, pwd = choice.credentials()
    print(f"  .env 位置   {choice.ENV_FILE}")
    print(f"  帐号        {'已配置：' + user if user else '未配置'}")
    print(f"  密码        {'已配置（长度 %d）' % len(pwd) if pwd else '未配置'}")

    try:
        api = choice._api()
        print(f"  EmQuantAPI  可导入（{getattr(api, '__file__', '?')}）")
    except ImportError as exc:
        print(f"  ✘ EmQuantAPI 不可导入：{exc}")
        print()
        print("  请先：")
        print("    1) 解压 EMQuantAPI_Python.zip")
        print("    2) 运行 EmQuantAPISetup.exe 安装")
        print("    3) 把 python3/EmQuantAPI.py 复制到 site-packages")
        print("    4) 在本包目录建 .env，写 CHOICE_USER / CHOICE_PASSWORD")
        return 1

    print()
    print("=" * 66)
    print("2. 启动并登录")
    print("=" * 66)
    state = choice.start()
    print(f"  {state['message']}")
    if not state["ok"]:
        return 1

    if len(sys.argv) < 2:
        print()
        print("启动成功。要实测指标，请再跑一次并带上股票代码：")
        print(f"    py {Path(__file__).name} 600519")
        choice.stop()
        return 0

    code = sys.argv[1]
    if code.isdigit():
        code = code + (".SH" if code[0] in "69" else ".SZ")

    print()
    print("=" * 66)
    print(f"3. 截面数据实测（{code}）")
    print("=" * 66)

    ok_names = []
    for name in CANDIDATES:
        res = choice.css(code, name)
        rows = res.get("data") or []
        good = bool(rows) and any(
            v not in (None, "", "--") for row in rows for v in row.values())
        print(f"  {'✔' if good else '✘'} {name:<32} {str(rows[:1])[:70] if good else ''}")
        if good:
            ok_names.append(name)

    print()
    print("=" * 66)
    print("4. 结果")
    print("=" * 66)
    print(f"  可用指标 {len(ok_names)} / {len(CANDIDATES)} 个")
    if ok_names:
        print("  可用清单：")
        print("    " + ", ".join(ok_names))
        print("  把这些填进 datasource/indicators_choice.json，并把 verified 置为 true。")

    choice.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
