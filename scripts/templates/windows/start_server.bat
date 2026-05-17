@echo off
chcp 65001 >nul 2>&1
title Video Transcriber

set PORTABLE_MODE=1
set PYTHON_DIR=%~dp0python
set PATH=%PYTHON_DIR%;%PYTHON_DIR%\Scripts;%~dp0ffmpeg;%PATH%
set PYTHONPATH=%~dp0app
set PYTHONNOUSERSITE=1
set MODELSCOPE_CACHE=%~dp0models_cache

if not exist "%~dp0temp" mkdir "%~dp0temp"
if not exist "%~dp0output" mkdir "%~dp0output"
if not exist "%~dp0logs" mkdir "%~dp0logs"

REM 联网轻量版：首次启动时自动下载 FFmpeg 和模型
if exist "%~dp0app\setup_runtime.py" (
    echo [检查] 运行环境组件 ...
    "%PYTHON_DIR%\python.exe" "%~dp0app\setup_runtime.py" --check >nul 2>&1
    if errorlevel 1 (
        echo 缺失组件，开始自动下载 ...
        "%PYTHON_DIR%\python.exe" "%~dp0app\setup_runtime.py"
    )
)

cd /d "%~dp0app"
"%PYTHON_DIR%\python.exe" -m uvicorn api.apimain:app --host 0.0.0.0 --port 8665
