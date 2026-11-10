@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "..\.venv-gesture\Scripts\python.exe" (
  "..\.venv-gesture\Scripts\python.exe" app.py
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  py -3.11 app.py
)
if errorlevel 1 pause
