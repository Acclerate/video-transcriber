@echo off
chcp 65001 >nul 2>&1
echo.
echo   ========================================
echo     Video Transcriber - 音视频转文本工具
echo     Starting...
echo   ========================================
echo.

start "Video Transcriber" /MIN "%~dp0start_server.bat"

timeout /t 5 /nobreak >nul
start http://localhost:8665

echo.
echo   Browser should open automatically.
echo   If not, visit: http://localhost:8665
echo   To stop: double-click 停止.bat
echo.
timeout /t 10 /nobreak >nul
