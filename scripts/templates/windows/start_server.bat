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

cd /d "%~dp0app"
"%PYTHON_DIR%\python.exe" -m uvicorn api.apimain:app --host 0.0.0.0 --port 8665
