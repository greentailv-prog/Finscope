"""Choice（东方财富）量化接口适配器 —— 作为 iFinD 的补充。

前置条件（一次性）：
  1. 解压 EMQuantAPI_Python.zip
  2. 运行 EmQuantAPISetup.exe 安装（会注册本机并激活）
  3. 把 python3/EmQuantAPI.py 复制到 site-packages（或把 libs 一起放好）
  4. 在本包目录建 .env，写入 CHOICE_USER / CHOICE_PASSWORD

**凭证只从本地文件或环境变量读取，不写进代码、不进日志。**

主要接口
--------
    c.start(options)                     启动并登录（选项串里带帐号密码）
    c.css(codes, indicators, options)    截面数据（单时点，如最新 PE/PB）
    c.csd(codes, indicators, 起, 止)     截面数据序列（历史，如近五年营收）
    c.csc(code, indicators, 起, 止)      板块成分（挑可比公司）
    c.ctr('SSE', ...)                    交易日历
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE.parent / ".env"
INDICATOR_FILE = HERE / "indicators.json"

_API = None
_STARTED = False


def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def credentials() -> tuple[str, str]:
    env = load_env()
    return (os.environ.get("CHOICE_USER") or env.get("CHOICE_USER", ""),
            os.environ.get("CHOICE_PASSWORD") or env.get("CHOICE_PASSWORD", ""))


def _api():
    global _API
    if _API is None:
        import EmQuantAPI  # noqa: PLC0415
        _API = EmQuantAPI
    return _API


def start() -> dict:
    """启动并登录。"""
    global _STARTED
    if _STARTED:
        return {"ok": True, "message": "已启动"}

    user, pwd = credentials()
    if not user or not pwd:
        return {"ok": False, "need_credentials": True,
                "message": f"未配置 Choice 帐号。请在 {ENV_FILE} 写入 "
                           f"CHOICE_USER / CHOICE_PASSWORD 两行。"}

    try:
        api = _api()
    except ImportError:
        return {"ok": False, "not_installed": True,
                "message": "未找到 EmQuantAPI 模块。请先运行 EmQuantAPISetup.exe 安装，"
                           "再把 python3/EmQuantAPI.py 复制到 site-packages。"}

    # Choice 的启动选项串格式：UserName=xxx,PassWord=xxx,ForceLogin=1
    options = f"UserName={user},PassWord={pwd},ForceLogin=1"
    try:
        code = api.c.start(options)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"启动异常：{type(exc).__name__}: {exc}"}

    # ErrorCode 0 = 成功
    err = getattr(code, "ErrorCode", None)
    if err in (0, None):
        _STARTED = True
        return {"ok": True, "code": err, "message": "启动成功"}
    return {"ok": False, "code": err,
            "message": f"启动失败（ErrorCode {err}）：{getattr(code, 'ErrorMsg', '')}"}


def stop() -> None:
    global _STARTED
    if _STARTED:
        try:
            _api().c.stop()
        except Exception:  # noqa: BLE001
            pass
        _STARTED = False


def _result_to_dict(result) -> list:
    """把 Choice 返回对象转成 records。"""
    data = getattr(result, "Data", None)
    if not data:
        return []
    out = []
    for code, payload in data.items():
        if isinstance(payload, dict):
            row = {"code": code}
            row.update({k: v for k, v in payload.items()})
            out.append(row)
        else:
            out.append({"code": code, "value": payload})
    return out


def css(codes: str, indicators: str) -> dict:
    """截面数据（单时点）。"""
    state = start()
    if not state["ok"]:
        return {"ok": False, "error": state["message"], **state}
    try:
        result = _api().c.css(codes, indicators, "")
        return {"ok": getattr(result, "ErrorCode", 0) == 0,
                "data": _result_to_dict(result),
                "raw_error": getattr(result, "ErrorMsg", "")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def csd(codes: str, indicators: str, startdate: str, enddate: str) -> dict:
    """截面数据序列（历史）。"""
    state = start()
    if not state["ok"]:
        return {"ok": False, "error": state["message"], **state}
    try:
        result = _api().c.csd(codes, indicators, startdate, enddate, "")
        return {"ok": getattr(result, "ErrorCode", 0) == 0,
                "data": _result_to_dict(result)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def sector_members(sector_code: str, startdate: str, enddate: str) -> dict:
    """板块成分股，用于挑可比公司。"""
    state = start()
    if not state["ok"]:
        return {"ok": False, "error": state["message"], **state}
    try:
        result = _api().c.csc(sector_code, "SECTOR_NAME", startdate, enddate, "")
        return {"ok": getattr(result, "ErrorCode", 0) == 0,
                "data": _result_to_dict(result)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def load_indicators() -> dict:
    """Choice 的指标映射单独放在一个文件，避免和 iFinD 的混在一起。"""
    path = HERE / "indicators_choice.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"verified": False}


def fetch(ticker: str, market: str = "A") -> dict:
    """按估值引擎需要的结构取数。"""
    state = start()
    if not state["ok"]:
        return {"ok": False, "source": "Choice", **{k: v for k, v in state.items()}}

    cfg = load_indicators()
    if not cfg.get("verified"):
        return {"ok": False, "source": "Choice",
                "error": "indicators_choice.json 尚未实测。请先跑 "
                         "tools/probe_choice.py 确认指标名有效。"}
    return {"ok": False, "source": "Choice", "error": "财务字段映射尚未配置。"}
