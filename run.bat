@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [run.bat] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [run.bat] Failed to create virtual environment. Is Python installed?
        pause
        exit /b 1
    )
)

echo [run.bat] Checking dependencies...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [run.bat] Failed to install dependencies.
    pause
    exit /b 1
)

echo [run.bat] Starting app...
".venv\Scripts\python.exe" -m app.main
if errorlevel 1 (
    echo [run.bat] App exited with an error.
    pause
    exit /b 1
)

endlocal
