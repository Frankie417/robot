@echo off
setlocal
cd /d "%~dp0"
"..\.venv-gesture\Scripts\python.exe" app.py
if errorlevel 1 pause
