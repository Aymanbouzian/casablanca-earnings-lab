@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m unittest discover -s tests
if errorlevel 1 goto error
".venv\Scripts\python.exe" run_demo.py
if errorlevel 1 goto error
start "" "outputs\demo\report.html"
pause
exit /b 0
:error
echo Read the error above. No orders were sent.
pause
exit /b 1
