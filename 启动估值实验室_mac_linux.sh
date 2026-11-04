#!/bin/sh
cd "$(dirname "$0")" || exit 1
printf '%s\n' '请先安装依赖: python -m pip install -r valuation/requirements.txt'
python -m uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010
