"""iFinD（同花顺）官方数据接口适配器。

前置条件（一次性）：
  1. 解压 THSDataInterface_Windows_*.zip
  2. 运行 bin/Tool/SuperCommand.exe 并用帐号登录（这一步会注册本机）
  3. 把 bin/x64/iFinDPy.py 复制到 Python 的 site-packages
  4. 在本目录建 .env，写入 IFIND_USER / IFIND_PASSWORD

**凭证只从本地文件或环境变量读取，不写进代码、不进日志、不回传前端。**

指标 ID 说明
------------
iFinD 用形如 `ths_pe_stock` 的指标 ID 取数。完整手册需从量化官网下载，
本包不内置。因此 `indicators.json` 里的 ID 是**可配置**的：
先用 tools/probe_ifind.py 实测哪些 ID 有效，再把结果固化进去。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE.parent / ".env"
INDICATOR_FILE = HERE / "indicators.json"

_LIBS = None
_LOGGED_IN = False


# ---------------------------------------------------------------- 凭证

def load_env() -> dict:
    """零依赖解析 .env。"""
    env = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            env[k.strip()] = v
    return env


def credentials() -> tuple[str, str]:
    env = load_env()
    user = os.environ.get("IFIND_USER") or env.get("IFIND_USER", "")
    pwd = os.environ.get("IFIND_PASSWORD") or env.get("IFIND_PASSWORD", "")
    return user, pwd


def load_indicators() -> dict:
    if INDICATOR_FILE.exists():
        try:
            return json.loads(INDICATOR_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


# ---------------------------------------------------------------- 连接

def _lib():
    """导入 iFinDPy。

    除了 site-packages，也接受把 `iFinDPy.py` 直接放在本目录——
    这样不用动系统 Python 环境。注意它还需要 iFinD 客户端的 DLL 与
    SuperCommand 登录后才能连上服务端。
    """
    global _LIBS
    if _LIBS is None:
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import iFinDPy  # noqa: PLC0415
        _LIBS = iFinDPy
    return _LIBS


def login() -> dict:
    """登录。返回 {ok, code, message}。凭证缺失时明确说明而不是静默失败。"""
    global _LOGGED_IN
    if _LOGGED_IN:
        return {"ok": True, "code": 0, "message": "已登录"}

    user, pwd = credentials()
    if not user or not pwd:
        return {"ok": False, "code": None, "need_credentials": True,
                "message": f"未配置 iFinD 帐号。请在 {ENV_FILE} 写入 "
                           f"IFIND_USER / IFIND_PASSWORD 两行。"}

    try:
        ths = _lib()
    except ImportError:
        return {"ok": False, "code": None, "not_installed": True,
                "message": "未找到 iFinDPy 模块。请先运行 SuperCommand.exe 登录，"
                           "再把 bin/x64/iFinDPy.py 复制到 site-packages。"}

    code = ths.THS_iFinDLogin(user, pwd)
    # 0 = 成功；-201 = 已登录（重复登录）
    if code in (0, -201):
        _LOGGED_IN = True
        return {"ok": True, "code": code, "message": "登录成功"}
    return {"ok": False, "code": code,
            "message": f"登录失败（返回码 {code}）。常见原因：帐号无数据接口权限、"
                       f"SuperCommand 未登录、或本机未注册。"}


def logout() -> None:
    global _LOGGED_IN
    if _LOGGED_IN:
        try:
            _lib().THS_iFinDLogout()
        except Exception:  # noqa: BLE001
            pass
        _LOGGED_IN = False


# ---------------------------------------------------------------- 取数

def _ths_code(ticker: str) -> str:
    """600519 -> 600519.SH；000858 -> 000858.SZ；AAPL -> AAPL.O"""
    raw = str(ticker).strip().upper()
    if "." in raw:
        return raw
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 6:
        if digits[0] in "69":
            return f"{digits}.SH"
        if digits[0] in "023":
            return f"{digits}.SZ"
        return f"{digits}.BJ"
    return f"{raw}.O"      # 美股默认纳斯达克/纽交所后缀


def basic_data(ticker: str, indicators: list[str], params: str = "") -> dict:
    """基础数据。indicators 为空时用 indicators.json 里的配置。"""
    state = login()
    if not state["ok"]:
        return {"ok": False, "error": state["message"], "login": state}

    ths = _lib()
    code = _ths_code(ticker)
    names = ";".join(indicators)
    try:
        raw = ths.THS_BasicData(code, names, params)
        df = ths.THS_Trans2DataFrame(raw)
        return {"ok": True, "code": code, "indicators": indicators,
                "data": df.to_dict(orient="records") if df is not None else []}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def date_serial(ticker: str, indicators: list[str], start: str, end: str,
                params: str = "") -> dict:
    """日期序列（历史财务数据的主力接口）。"""
    state = login()
    if not state["ok"]:
        return {"ok": False, "error": state["message"], "login": state}

    ths = _lib()
    code = _ths_code(ticker)
    try:
        raw = ths.THS_DateSerial(code, ";".join(indicators), params, "", start, end)
        df = ths.THS_Trans2DataFrame(raw)
        return {"ok": True, "code": code,
                "data": df.to_dict(orient="records") if df is not None else []}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def iwencai(query: str, domain: str = "stock") -> dict:
    """i问财：自然语言取数。

    不知道指标 ID 时的探路工具，例：「贵州茅台2024年营业收入」。
    """
    state = login()
    if not state["ok"]:
        return {"ok": False, "error": state["message"]}
    try:
        return {"ok": True, "data": _lib().THS_iwencai(query, domain)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def industry_peers(ticker: str, block: str = "") -> dict:
    """按同花顺行业指数取成分股，用于挑可比公司。

    block 留空时用「所属同花顺行业」的默认板块。
    """
    state = login()
    if not state["ok"]:
        return {"ok": False, "error": state["message"]}
    ths = _lib()
    today = date.today().strftime("%Y-%m-%d")
    try:
        raw = ths.THS_DataPool("block", f"{today};{block}",
                               "date:Y,thscode:Y,security_name:Y")
        df = ths.THS_Trans2DataFrame(raw)
        return {"ok": True, "data": df.to_dict(orient="records") if df is not None else []}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def risk_free_10y(start: str | None = None) -> dict:
    """10 年期国债收益率（DCF 的无风险利率）。用 EDB 宏观库。"""
    state = login()
    if not state["ok"]:
        return {"ok": False, "error": state["message"]}
    ths = _lib()
    end = date.today().strftime("%Y-%m-%d")
    start = start or (date.today() - timedelta(days=60)).strftime("%Y-%m-%d")
    try:
        # 中国 10 年期国债到期收益率（中债）在 EDB 里的常见代码
        raw = ths.THS_EDB("M032568668", start, end)
        df = ths.THS_Trans2DataFrame(raw)
        return {"ok": True, "data": df.to_dict(orient="records") if df is not None else []}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------- 统一入口

def fetch(ticker: str, market: str = "A") -> dict:
    """按估值引擎需要的结构取数。指标 ID 取自 indicators.json。"""
    state = login()
    if not state["ok"]:
        return {"ok": False, "error": state["message"], "source": "iFinD",
                **{k: v for k, v in state.items() if k != "message"}}

    cfg = load_indicators()
    if not cfg.get("verified"):
        return {"ok": False, "source": "iFinD",
                "error": "indicators.json 尚未实测。请先运行 tools/probe_ifind.py "
                         "确认指标 ID 有效，再把 verified 置为 true。"}

    # 这里留出接入点：拿到实测有效的指标 ID 后，把返回值映射成引擎的 financials 结构
    return {"ok": False, "source": "iFinD",
            "error": "已登录，但财务字段映射尚未配置。请先用 probe_ifind.py 实测指标。"}
