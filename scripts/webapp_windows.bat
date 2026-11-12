@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo Run scripts\install_windows.bat first.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8501 in your browser. Press Ctrl+C here to stop.
.venv\Scripts\python.exe -m catwatch --config config.windows.json web
if errorlevel 1 pause
