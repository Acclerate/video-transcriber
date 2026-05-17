@echo off
chcp 65001 >nul 2>&1
setlocal

:: 拖拽文件到此脚本上即可生成字幕
:: 使用 batch 模式，模型只加载一次

set "SCRIPT_DIR=%~dp0"
set "PYTHON=%SCRIPT_DIR%webmain.py"

if "%~1"=="" (
    echo.
    echo   用法: 将视频/音频文件拖拽到此脚本上
    echo   支持格式: mp4, avi, mkv, mov, mp3, wav, m4a ...
    echo.
    pause
    exit /b 1
)

:: 写入临时文件列表，用 batch 模式一次性处理
set "tmpfile=%TEMP%\vt_batch_%RANDOM%.txt"
(for %%f in (%*) do echo %%~f) > "%tmpfile%"

python "%PYTHON%" batch "%tmpfile%" --format srt --output-dir "%~dp0字幕输出"

del "%tmpfile%"

echo.
echo 全部处理完成!
pause
