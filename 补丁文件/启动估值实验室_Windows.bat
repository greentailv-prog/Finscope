@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%FINSCOPE_PYTHON%"
if not defined PY if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY set "PY=python"
echo [FinScope 2.0] 估值服务启动中...
echo 运行前请先执行：%PY% -m pip install -r valuation\requirements.txt
echo 如需 18 表底稿，请确认 artifact_tool / artifact_tool_v2 可用；
echo 或设置 FINSCOPE_ARTIFACT_TOOL_PATH 指向其 site-packages。
echo 浏览器访问 http://127.0.0.1:8010/ui/valuation_lab.html
echo Ctrl+C 退出
"%PY%" -m uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010
pause
