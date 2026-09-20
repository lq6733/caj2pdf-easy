@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  where python3 >nul 2>&1 && set "PY=python3"
)

if not defined PY (
  echo 还没有安装 Python。
  echo 请打开 https://www.python.org/downloads/windows/
  echo 安装时务必勾选 “Add python.exe to PATH”。
  pause
  start "" "https://www.python.org/downloads/windows/"
  exit /b 1
)

if exist ".venv\Scripts\pythonw.exe" if exist ".venv\.caj2pdf-ready" (
  start "" ".venv\Scripts\pythonw.exe" -m app %*
  exit /b 0
)

%PY% -m app %*
if errorlevel 1 pause
