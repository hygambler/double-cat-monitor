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
set CATWATCH_CONFIG=config.windows.json
.venv\Scripts\python.exe -m catwatch --config config.windows.json demo
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m streamlit run dashboard.py
:failed
pause
