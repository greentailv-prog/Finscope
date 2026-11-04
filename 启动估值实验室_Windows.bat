@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [FinScope 2.0] 估值服务启动中...
echo 运行前请先执行：python -m pip install -r valuation\requirements.txt
echo 浏览器访问 http://127.0.0.1:8010/ui/valuation_lab.html
echo Ctrl+C 退出
python -m uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010
pause
