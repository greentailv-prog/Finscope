"""可插拔数据层。

主程序（可能只装了 openpyxl）通过 subprocess 把取数任务交给「数据 Python」，
再读回 JSON。解释器与数据源都可插拔：

    数据解释器优先级：FINSCOPE_DATA_PYTHON > iFinD 自带运行时 > 当前解释器
    数据源优先级：    iFinD 官方接口 > Choice 官方接口 > akshare(A股)/yfinance(美股)

iFinD / Choice 的 Python 接口包装好后，放进本目录即可自动启用——
`IFIND_AVAILABLE` / `CHOICE_AVAILABLE` 探测通过就会优先走官方源。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WORKER = Path(__file__).resolve().parent / "worker.py"
TIMEOUT_FINANCIALS = 300
TIMEOUT_QUICK = 120

_PROBE_CACHE: dict | None = None


# ---------------------------------------------------------------- 解释器探测


def _candidates() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    override = os.environ.get("FINSCOPE_DATA_PYTHON")
    if override:
        out.append(("环境变量 FINSCOPE_DATA_PYTHON", override))

    # iFinD 自带运行时：装在哪一层不确定，在各盘根下找
    rel = Path("FinWork/resources/skill-python/runtime/win32-x64/python/python.exe")
    for drive in ("D:/", "C:/", "E:/"):
        root = Path(drive)
        if not root.exists():
            continue
        direct = root / "iFinD" / rel
        if direct.exists():
            out.append(("iFinD 自带运行时", str(direct)))
        try:
            for found in root.glob(f"*/iFinD/{rel.as_posix()}"):
                out.append(("iFinD 自带运行时", str(found)))
            for found in root.glob(f"*/*/iFinD/{rel.as_posix()}"):
                out.append(("iFinD 自带运行时", str(found)))
        except OSError:
            continue

    if sys.platform == "win32":
        import shutil
        py = shutil.which("py")
        if py:
            out.append(("本机 py 启动器", py))
    out.append(("当前解释器", sys.executable))

    seen: set[str] = set()
    unique = []
    for label, path in out:
        key = path.lower()
        if key not in seen:
            seen.add(key)
            unique.append((label, path))
    return unique


def _can_import(python: str, module: str) -> bool:
    try:
        proc = subprocess.run(
            [python, "-c", f"import {module}"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "NO_PROXY": "*", "no_proxy": "*", "PYTHONIOENCODING": "utf-8"},
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def probe(force: bool = False) -> dict:
    """挑一个能 import akshare 或 yfinance 的解释器。结果缓存。"""
    global _PROBE_CACHE
    if _PROBE_CACHE is not None and not force:
        return _PROBE_CACHE

    tried = []
    for label, path in _candidates():
        if not Path(path).exists() and path != sys.executable:
            tried.append({"label": label, "path": path, "ok": False, "reason": "不存在"})
            continue
        for module in ("akshare", "yfinance"):
            if _can_import(path, module):
                _PROBE_CACHE = {"ok": True, "path": path, "label": label,
                                "module": module, "tried": tried}
                return _PROBE_CACHE
        tried.append({"label": label, "path": path, "ok": False,
                      "reason": "akshare 与 yfinance 都不可用"})

    _PROBE_CACHE = {"ok": False, "path": None, "label": None, "tried": tried,
                    "reason": "找不到能取数的 Python 解释器"}
    return _PROBE_CACHE


def data_python() -> str:
    info = probe()
    if not info["ok"]:
        raise RuntimeError(info.get("reason", "找不到数据解释器"))
    return info["path"]


# ---------------------------------------------------------------- 官方接口探测

def _official_available(module_name: str) -> bool:
    """iFinD / Choice 的官方 Python 包是否可用。

    包名分别是 iFinDPy 与 EmQuantAPI。装好后放进本目录或 site-packages 即可。
    """
    try:
        __import__(module_name)
        return True
    except ImportError:
        local = Path(__file__).resolve().parent / module_name
        return local.exists()


IFIND_AVAILABLE = _official_available("iFinDPy")
CHOICE_AVAILABLE = _official_available("EmQuantAPI")


def source_priority() -> list[str]:
    """当前生效的数据源优先级。"""
    if IFIND_AVAILABLE:
        return ["iFinD 官方接口", "akshare / yfinance"]
    if CHOICE_AVAILABLE:
        return ["Choice 官方接口", "akshare / yfinance"]
    return ["akshare（A股）/ yfinance（美股）"]


# ---------------------------------------------------------------- 调用


def _run(payload: dict, timeout: int) -> dict:
    python = data_python()
    with tempfile.TemporaryDirectory(prefix="fs_val_") as tmp:
        req = Path(tmp) / "request.json"
        res = Path(tmp) / "response.json"
        req.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            proc = subprocess.run(
                [python, str(WORKER), str(req), str(res)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout, cwd=tmp,
                env={**os.environ, "NO_PROXY": "*", "no_proxy": "*",
                     "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"取数超时（{timeout}s）"}
        except OSError as exc:
            return {"ok": False, "error": f"无法启动数据解释器：{exc}"}

        if not res.exists():
            tail = ((proc.stderr or "") + (proc.stdout or ""))[-700:]
            return {"ok": False, "error": f"工作进程未产出结果。{tail}"}
        return json.loads(res.read_text(encoding="utf-8"))


def fetch(ticker: str, market: str | None = None) -> dict:
    """取一家公司的基础数据。

    market 留空时自动判断：6 位数字 → A 股；其余 → 美股。
    """
    if market is None:
        market = "A" if str(ticker).strip().isdigit() else "US"

    # 官方接口优先（装好后自动生效）
    if IFIND_AVAILABLE:
        try:
            from . import ifind
            result = ifind.fetch(ticker, market)
            if result.get("ok"):
                return result
        except Exception:  # noqa: BLE001
            pass
    if CHOICE_AVAILABLE:
        try:
            from . import choice
            result = choice.fetch(ticker, market)
            if result.get("ok"):
                return result
        except Exception:  # noqa: BLE001
            pass

    if market == "A":
        return _run({"action": "ashare", "code": ticker}, TIMEOUT_FINANCIALS)
    return _run({"action": "us", "ticker": ticker}, TIMEOUT_FINANCIALS)


def health() -> dict:
    info = probe()
    result = {
        "data_python": info.get("path"),
        "data_python_label": info.get("label"),
        "usable_module": info.get("module"),
        "ifind": IFIND_AVAILABLE,
        "choice": CHOICE_AVAILABLE,
        "source_priority": source_priority(),
    }
    if info["ok"]:
        result.update(_run({"action": "health"}, TIMEOUT_QUICK))
    else:
        result["ok"] = False
        result["reason"] = info.get("reason")
    return result
