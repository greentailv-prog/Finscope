"""artifact_tool 运行时定位。

不同交付环境把同一个 SpreadsheetFile/Workbook 运行时装成
`artifact_tool` 或 `artifact_tool_v2`；这里统一探测，避免 18 表底稿
因为包名不同而静默降级成 12 表。

可用 `FINSCOPE_ARTIFACT_TOOL_PATH` 追加一个 site-packages 目录。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_paths():
    extra = os.environ.get("FINSCOPE_ARTIFACT_TOOL_PATH", "")
    for item in extra.split(os.pathsep):
        item = item.strip()
        if item:
            yield item
    # 本机若存在 codex runtime，自动把它加入搜索路径，不写死用户名。
    for base in (
        Path.home() / ".cache" / "codex-runtimes",
        Path.home() / ".codex" / "runtime",
    ):
        if base.exists():
            for item in base.glob("*/dependencies/python/Lib/site-packages"):
                yield str(item)


def load_artifact_tool():
    try:
        from artifact_tool import Workbook, SpreadsheetFile  # type: ignore
        return Workbook, SpreadsheetFile
    except ImportError:
        pass

    for item in _candidate_paths():
        if item not in sys.path:
            sys.path.append(item)

    try:
        from artifact_tool_v2 import Workbook, SpreadsheetFile  # type: ignore
        return Workbook, SpreadsheetFile
    except ImportError as exc:
        raise ImportError(
            "未找到 artifact_tool 或 artifact_tool_v2；"
            "18 表底稿需要该运行时，否则自动回退 12 表兼容底稿。"
        ) from exc
