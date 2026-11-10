@echo off
setlocal
cd /d "%~dp0"
py -3.11 --version
if errorlevel 1 goto fail
if not exist ".venv-gesture\Scripts\python.exe" py -3.11 -m venv .venv-gesture
if errorlevel 1 goto fail
".venv-gesture\Scripts\python.exe" -m pip install -r requirements_windows.txt
if errorlevel 1 goto fail
".venv-gesture\Scripts\python.exe" -m pip check
if errorlevel 1 goto fail
echo Installation complete. Run start_week7.bat.
pause
exit /b 0
:fail
echo Installation failed. Check Python 3.11 and the error above.
pause
exit /b 1
