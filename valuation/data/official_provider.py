"""iFinD / Choice 官方数据源适配器（与 A 共用同一套账号与客户端）。

现状：
  · 本机未安装 iFinDPy / EmQuantAPI，也没有客户端 DLL 与账号凭证；
  · 因此 `probe_*()` 会返回 available=False，估值自动回退到 web / akshare；
  · A 接入官方源后，只要在本机装好客户端并在 `valuation/.env` 写入账号，
    这里会自动启用，无需改估值代码。

凭证只从环境变量或 valuation/.env 读取，不写进代码、不进日志、不回传前端。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
EXTRACT_THS = ROOT / "_extract" / "ths"
EXTRACT_CHOICE = ROOT / "_extract" / "choice"

_IFIND = None
_CHOICE = None
_IFIND_LOGGED = False
_CHOICE_STARTED = False


def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _credentials(prefix: str) -> tuple[str, str]:
    env = load_env()
    user = os.environ.get(f"{prefix}_USER") or env.get(f"{prefix}_USER", "")
    pwd = os.environ.get(f"{prefix}_PASSWORD") or env.get(f"{prefix}_PASSWORD", "")
    return user, pwd


# ======================================================================
# iFinD
# ======================================================================


def _silent_import(name: str):
    """导入厂商包装时屏蔽它们自己的 print（iFinDPy 会打印 .pth 路径）。"""
    import contextlib
    import importlib
    import io
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return importlib.import_module(name)


def _ifind_module():
    global _IFIND
    if _IFIND is not None:
        return _IFIND
    try:
        _IFIND = _silent_import("iFinDPy")
        return _IFIND
    except Exception:  # noqa: BLE001
        pass
    if EXTRACT_THS.exists():
        if str(EXTRACT_THS) not in sys.path:
            sys.path.insert(0, str(EXTRACT_THS))
        try:
            _IFIND = _silent_import("iFinDPy")
            return _IFIND
        except Exception:  # noqa: BLE001
            return None
    return None


def _dll_exists(root: Path, *rels: str) -> bool:
    return any((root / rel).exists() for rel in rels)


def probe_ifind() -> dict:
    user, pwd = _credentials("IFIND")
    mod = _ifind_module()
    dll = _dll_exists(EXTRACT_THS, "x64/FTDataInterface.dll", "FTDataInterface.dll")
    out = {
        "source": "iFinD",
        "installed": mod is not None,
        "dll_present": dll,
        "credentials": bool(user and pwd),
        "available": False,
        "message": "",
    }
    if mod is None:
        out["message"] = ("未找到 iFinDPy 模块。需要先安装同花顺 iFinD 客户端、运行 "
                          "SuperCommand.exe 登录，并把 iFinDPy.py 与 x64 DLL 放进 Python 环境。")
        return out
    if not dll:
        out["message"] = "已找到 iFinDPy.py，但缺少 x64/FTDataInterface.dll，无法连接服务端。"
        return out
    if not user or not pwd:
        out["message"] = "已找到 iFinDPy，但未配置 IFIND_USER / IFIND_PASSWORD。"
        return out
    try:
        code = mod.THS_iFinDLogin(user, pwd)
        out["login_code"] = code
        out["available"] = code in (0, -201)
        out["message"] = "登录成功" if out["available"] else f"登录失败（返回码 {code}）"
    except Exception as exc:  # noqa: BLE001
        out["message"] = f"登录异常：{type(exc).__name__}: {str(exc)[:120]}"
    return out


def _ifind_login() -> dict:
    global _IFIND_LOGGED
    state = probe_ifind()
    if not state.get("available"):
        return state
    _IFIND_LOGGED = True
    return state


def _ifind_code(ticker: str) -> str:
    raw = str(ticker).strip().upper()
    if "." in raw:
        return raw
    code = "".join(c for c in raw if c.isdigit()).zfill(6)
    if code[0] == "6":
        return f"{code}.SH"
    if code[0] in ("0", "3"):
        return f"{code}.SZ"
    return f"{code}.BJ"


def _ifind_series(ticker: str, indicators: list[str], years: int = 6) -> list[dict]:
    mod = _ifind_module()
    if mod is None:
        return []
    code = _ifind_code(ticker)
    end = date.today()
    start = end - timedelta(days=365 * (years + 1))
    raw = mod.THS_DateSerial(code, ";".join(indicators), "", "",
                             start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    df = mod.THS_Trans2DataFrame(raw)
    if df is None or df.empty:
        return []
    return df.to_dict(orient="records")


def fetch_ifind(ticker: str) -> dict:
    """按估值引擎结构取数。指标 ID 未实测时返回明确错误，不猜。"""
    state = _ifind_login()
    if not state.get("available"):
        return {"ok": False, "source": "iFinD", "error": state.get("message"),
                "probe": state}
    # 指标 ID 需要按账号权限实测；未配置 verified 映射前不启用。
    verified_file = ROOT / "config" / "ifind_verified.json"
    if not verified_file.exists():
        return {"ok": False, "source": "iFinD",
                "error": "已登录，但 config/ifind_verified.json 尚未实测。"
                         "请运行 `python cli.py probe-ifind` 生成指标映射。"}
    import json
    cfg = json.loads(verified_file.read_text(encoding="utf-8"))
    mapping = cfg.get("mapping") or {}
    if not mapping:
        return {"ok": False, "source": "iFinD", "error": "ifind_verified.json 没有 mapping。"}
    rows = _ifind_series(ticker, list(mapping.values()))
    if not rows:
        return {"ok": False, "source": "iFinD", "error": "iFinD 未返回序列数据。"}
    return {"ok": True, "source": "iFinD", "rows": rows, "mapping": mapping,
            "note": "iFinD 原始序列；字段映射需按 verified 配置继续标准化。"}


# ======================================================================
# Choice
# ======================================================================


def _choice_module():
    global _CHOICE
    if _CHOICE is not None:
        return _CHOICE
    try:
        _CHOICE = _silent_import("EmQuantAPI")
        return _CHOICE
    except Exception:  # noqa: BLE001
        pass
    if EXTRACT_CHOICE.exists():
        if str(EXTRACT_CHOICE) not in sys.path:
            sys.path.insert(0, str(EXTRACT_CHOICE))
        try:
            _CHOICE = _silent_import("EmQuantAPI")
            return _CHOICE
        except Exception:  # noqa: BLE001
            return None
    return None


def probe_choice() -> dict:
    user, pwd = _credentials("CHOICE")
    mod = _choice_module()
    dll = _dll_exists(EXTRACT_CHOICE, "libs/windows/EmQuantAPI_x64.dll",
                      "libs/windows/EmQuantAPI.dll", "EmQuantAPI_x64.dll")
    out = {
        "source": "Choice",
        "installed": mod is not None,
        "dll_present": dll,
        "credentials": bool(user and pwd),
        "available": False,
        "message": "",
    }
    if mod is None:
        out["message"] = ("未找到 EmQuantAPI 模块。需要先运行 EmQuantAPISetup.exe 安装客户端，"
                          "并把 EmQuantAPI.py 与 DLL 放进 Python 环境。")
        return out
    if not dll:
        out["message"] = "已找到 EmQuantAPI.py，但缺少 libs/windows/EmQuantAPI_x64.dll，无法连接服务端。"
        return out
    if not user or not pwd:
        out["message"] = "已找到 EmQuantAPI 与 DLL，但未配置 CHOICE_USER / CHOICE_PASSWORD。"
        return out
    try:
        code = mod.c.start(f"UserName={user},PassWord={pwd},ForceLogin=1")
        err = getattr(code, "ErrorCode", None)
        out["login_code"] = err
        out["available"] = err in (0, None)
        out["message"] = "启动成功" if out["available"] else f"启动失败（ErrorCode {err}）"
    except Exception as exc:  # noqa: BLE001
        out["message"] = f"启动异常：{type(exc).__name__}: {str(exc)[:120]}"
    return out


def fetch_choice(ticker: str) -> dict:
    state = probe_choice()
    if not state.get("available"):
        return {"ok": False, "source": "Choice", "error": state.get("message"),
                "probe": state}
    verified_file = ROOT / "config" / "choice_verified.json"
    if not verified_file.exists():
        return {"ok": False, "source": "Choice",
                "error": "已登录，但 config/choice_verified.json 尚未实测。"
                         "请运行 `python cli.py probe-choice` 生成指标映射。"}
    return {"ok": False, "source": "Choice",
            "error": "Choice 指标映射已存在，但当前版本只完成探测；"
                     "正式取数请由 A 的统一数据层注入，或补全 fetch_choice 的字段标准化。"}


def probe_all() -> dict:
    return {"iFinD": probe_ifind(), "Choice": probe_choice()}
