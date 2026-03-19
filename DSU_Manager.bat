@echo off
cd /D "%~dp0"
echo ========================================================
echo   DSUComfyCG - Starting Manager Environment
echo ========================================================
echo.

:: Auto-Update from GitHub
echo [INFO] Checking for updates from GitHub...
git pull
echo.

:: Check for Python 3.10+
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from the Microsoft Store or python.org.
    pause
    exit /b
)

:: Ensure .venv exists
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating Python Virtual Environment ^(.venv^)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment. 
        pause
        exit /b
    )
)

:: Activate venv and install dependencies
echo [INFO] Installing required UI dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
python -m pip install PySide6 requests --no-warn-script-location >nul 2>&1

:: Run the Manager
echo [INFO] Launching DSUComfyCG Manager...
python Manager\main.py

if %errorlevel% neq 0 (
    echo.
    echo -------------------------------------------------------------------------
    echo Manager UI crashed or encountered an error.
    echo -------------------------------------------------------------------------
    pause
)

:: Deactivate upon exit
deactivate >nul 2>&1
