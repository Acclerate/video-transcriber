@echo off
taskkill /F /FI "WINDOWTITLE eq Video Transcriber*" >nul 2>&1
echo Server stopped.
timeout /t 3 /nobreak >nul
