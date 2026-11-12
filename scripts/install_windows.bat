@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 was not found. Install Python 3.12 with the Python launcher first.
  goto failed
)
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto failed
rem Use the official CUDA 12.8 wheel index; NVIDIA driver must support this runtime.
.venv\Scripts\python.exe -m pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -e . pytest
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m catwatch --config config.windows.json doctor --model
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pytest -q
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip freeze > data\windows-installed.txt
if errorlevel 1 goto failed
echo Installation and GPU checks passed. See WINDOWS_SETUP.md for camera setup.
pause
exit /b 0
:failed
echo Setup stopped. Keep this window open and share the error above in the PC chat.
pause
exit /b 1
