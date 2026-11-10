@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist ".venv-gesture\Scripts\python.exe" (
  ".venv-gesture\Scripts\python.exe" week7_gesture_control.py
) else if exist "..\5.目标识别(已修改)\.venv-gesture\Scripts\python.exe" (
  "..\5.目标识别(已修改)\.venv-gesture\Scripts\python.exe" week7_gesture_control.py
) else (
  py -3.11 week7_gesture_control.py
)
if errorlevel 1 (
  echo Run install_windows.bat first if dependencies are missing.
  pause
)
