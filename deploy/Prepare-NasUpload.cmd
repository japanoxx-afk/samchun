@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare-NasUpload.ps1"
explorer "%~dp0upload\samchun-live\app"
echo.
echo Press any key to close.
pause >nul
