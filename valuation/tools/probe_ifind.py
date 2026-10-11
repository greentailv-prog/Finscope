"""iFinD 连通性 + 指标 ID 实测。

装好接口、配好帐号后跑这个：

    py valuation/tools/probe_ifind.py            # 只测连通
    py valuation/tools/probe_ifind.py 600519     # 再测指标

它会：
  1. 检查 iFinDPy 是否可导入、帐号是否配好
  2. 尝试登录
  3. 逐个试 indicators.json 里的候选指标，报告哪些有效
  4. 试 i问财（自然语言取数）作为备选路径

**不会打印密码。**
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datasource import ifind  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("1. 环境检查")
    print("=" * 70)

    user, pwd = ifind.credentials()
    print(f"  .env 位置     {ifind.ENV_FILE}")
    print(f"  帐号          {'已配置：' + user if user else '未配置'}")
    print(f"  密码          {'已配置（长度 %d）' % len(pwd) if pwd else '未配置'}")

    try:
        mod = ifind._lib()
        print(f"  iFinDPy 模块  可导入（{getattr(mod, '__file__', '?')}）")
    except ImportError as exc:
        print(f"  ✘ iFinDPy 模块  不可导入：{exc}")
        print()
        print("  请先：")
        print("    1) 解压 THSDataInterface_Windows_*.zip")
        print("    2) 运行 bin/Tool/SuperCommand.exe 用帐号登录")
        print("    3) 把 bin/x64/iFinDPy.py 复制到 site-packages")
        print("    4) 在本包目录建 .env，写 IFIND_USER / IFIND_PASSWORD")
        return 1

    print()
    print("=" * 70)
    print("2. 登录")
    print("=" * 70)
    state = ifind.login()
    print(f"  {state['message']}")
    if not state["ok"]:
        return 1

    if len(sys.argv) < 2:
        print()
        print("登录成功。要实测指标，请再跑一次并带上股票代码：")
        print(f"    py {Path(__file__).name} 600519")
        ifind.logout()
        return 0

    ticker = sys.argv[1]
    print()
    print("=" * 70)
    print(f"3. 指标实测（{ticker}）")
    print("=" * 70)

    cfg = json.loads(ifind.INDICATOR_FILE.read_text(encoding="utf-8"))
    candidates = cfg.get("_候选指标", {})
    verified: dict[str, str] = {}

    for field, names in candidates.items():
        hit = None
        for name in names:
            res = ifind.basic_data(ticker, [name])
            if res.get("ok"):
                rows = res.get("data") or []
                if rows and any(v not in (None, "", "--") for v in rows[0].values()):
                    hit = name
                    break
        mark = "✔" if hit else "✘"
        print(f"  {mark} {field:<18} {hit or '（候选都无效）'}")
        if hit:
            verified[field] = hit

    print()
    print("=" * 70)
    print("4. i问财探路（不知道指标 ID 时用这个）")
    print("=" * 70)
    for q in (f"{ticker} 2024年营业收入", f"{ticker} 2024年净利润", f"{ticker} 市盈率"):
        res = ifind.iwencai(q)
        ok = res.get("ok")
        print(f"  {'✔' if ok else '✘'} {q}")
        if ok:
            print(f"      {str(res.get('data'))[:160]}")

    print()
    print("=" * 70)
    print("5. 结果")
    print("=" * 70)
    print(f"  实测可用指标 {len(verified)} / {len(candidates)} 个")
    if verified:
        print("  把这些填进 datasource/indicators.json 的 _已验证指标，并把 verified 置为 true：")
        print(json.dumps(verified, ensure_ascii=False, indent=4))

    ifind.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
