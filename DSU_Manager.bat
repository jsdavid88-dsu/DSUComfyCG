@echo off
cd /D "%~dp0"
echo ========================================================
echo   DSUComfyCG - Starting Manager Environment
echo ========================================================
echo.

:: Auto-Update from GitHub
echo [INFO] Checking for updates from GitHub...
git pull 2>nul
echo.

:: ============================================================
:: PYTHON RESOLUTION: System Python -> Embedded Python (fallback)
:: ============================================================
set "PYTHON_EXE="
set "USING_EMBEDDED=0"

:: 1) Try system Python first
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    echo [OK] System Python found.
    goto :python_ready
)

:: 2) Try existing embedded Python
if exist "python_embeded\python.exe" (
    set "PYTHON_EXE=%~dp0python_embeded\python.exe"
    set "USING_EMBEDDED=1"
    echo [OK] Embedded Python found.
    goto :python_ready
)

:: 3) No Python at all - auto-download embedded Python 3.12
echo [WARN] Python not found on this system!
echo [INFO] Downloading Python 3.12 Embedded (one-time setup)...
echo.

set "PY_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
set "PY_ZIP=%TEMP%\python_embedded.zip"
set "PY_DIR=%~dp0python_embeded"

:: Download using PowerShell (available on all modern Windows)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_ZIP%'"

if not exist "%PY_ZIP%" (
    echo [ERROR] Failed to download Python. Check internet connection.
    pause
    exit /b
)

:: Extract
echo [INFO] Extracting to python_embeded\...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Expand-Archive -Path '%PY_ZIP%' -DestinationPath '%PY_DIR%' -Force"

del "%PY_ZIP%" 2>nul

:: Enable pip by uncommenting import site in python312._pth
echo [INFO] Enabling pip support...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Content '%PY_DIR%\python312._pth') -replace '#import site','import site' | Set-Content '%PY_DIR%\python312._pth'"

:: Install pip via get-pip.py
echo [INFO] Installing pip...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%PY_DIR%\get-pip.py'"
"%PY_DIR%\python.exe" "%PY_DIR%\get-pip.py" --no-warn-script-location >nul 2>&1

echo [OK] Embedded Python 3.12 installed successfully!
echo.

set "PYTHON_EXE=%~dp0python_embeded\python.exe"
set "USING_EMBEDDED=1"

:python_ready
echo [INFO] Using: %PYTHON_EXE%
echo.

:: ============================================================
:: VIRTUAL ENVIRONMENT SETUP
:: ============================================================
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating Python Virtual Environment ^(.venv^)...
    "%PYTHON_EXE%" -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b
    )
)

:: Clear __pycache__ to avoid stale .pyc issues on network drives
if exist "Manager\__pycache__" rd /s /q "Manager\__pycache__" >nul 2>&1
if exist "Manager\ui\__pycache__" rd /s /q "Manager\ui\__pycache__" >nul 2>&1
if exist "Manager\core\__pycache__" rd /s /q "Manager\core\__pycache__" >nul 2>&1

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
