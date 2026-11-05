#!/bin/sh
cd "$(dirname "$0")" || exit 1
PY="${FINSCOPE_PYTHON:-}"
if [ -z "$PY" ] && [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; fi
if [ -z "$PY" ]; then PY="python"; fi
printf '%s\n' "请先安装依赖: $PY -m pip install -r valuation/requirements.txt"
printf '%s\n' "18 表底稿需要 artifact_tool / artifact_tool_v2，可设置 FINSCOPE_ARTIFACT_TOOL_PATH。"
"$PY" -m uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010
