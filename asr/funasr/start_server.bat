@echo off
chcp 65001 >nul
echo ========================================
echo   FunASR WebSocket 服务启动器
echo   websockets 16.0+ 新API版本
echo ========================================

cd /d "%~dp0"

REM 使用独立venv环境
if exist "venv\Scripts\python.exe" (
    echo [INFO] 使用独立venv环境
    call venv\Scripts\activate.bat
    echo [INFO] Python: venv\Scripts\python.exe
    venv\Scripts\python.exe -c "import websockets; print(f'websockets版本: {websockets.__version__}')"
    venv\Scripts\python.exe ASR_server.py
) else (
    echo [WARN] venv不存在，使用系统Python
    python ASR_server.py
)

pause
