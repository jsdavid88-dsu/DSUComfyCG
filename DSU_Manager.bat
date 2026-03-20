@echo off
cd /D "%~dp0"
echo ========================================================
echo   DSUComfyCG - Starting Manager Environment
echo ========================================================
echo.

:: ============================================================
:: GIT RESOLUTION: System Git -> Portable Git (auto-install)
:: ============================================================
set "GIT_EXE=git"

git --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Git found.
) else (
    if exist "git_portable\cmd\git.exe" (
        set "GIT_EXE=%~dp0git_portable\cmd\git.exe"
        set "PATH=%~dp0git_portable\cmd;%PATH%"
        echo [OK] Portable Git found.
    ) else (
        echo [WARN] Git not found on this system!
        echo [INFO] Downloading MinGit portable (~30MB, one-time setup)...
        
        set "GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.2/MinGit-2.47.1.2-64-bit.zip"
        set "GIT_ZIP=%TEMP%\mingit.zip"
        set "GIT_DIR=%~dp0git_portable"
        
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%GIT_URL%' -OutFile '%GIT_ZIP%'"
        
        if not exist "%GIT_ZIP%" (
            echo [ERROR] Failed to download Git. Check internet connection.
            echo [INFO] You can manually install Git from https://git-scm.com
            echo [INFO] Continuing without auto-update...
            goto :skip_git
        )
        
        echo [INFO] Extracting to git_portable\...
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "Expand-Archive -Path '%GIT_ZIP%' -DestinationPath '%GIT_DIR%' -Force"
        del "%GIT_ZIP%" 2>nul
        
        set "GIT_EXE=%~dp0git_portable\cmd\git.exe"
        set "PATH=%~dp0git_portable\cmd;%PATH%"
        echo [OK] MinGit installed successfully!
    )
)

:: ============================================================
:: AUTO-UPDATE from GitHub
:: ============================================================
"%GIT_EXE%" rev-parse --is-inside-work-tree >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Checking for updates from GitHub...
    "%GIT_EXE%" pull 2>nul
    "%GIT_EXE%" submodule update --init --recursive 2>nul
) else (
    echo [INFO] Not a git repository - skipping auto-update.
    echo        To enable: git clone https://github.com/jsdavid88-dsu/DSUComfyCG.git
)

:skip_git
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
echo [INFO] Downloading Python 3.12 Embedded (~15MB, one-time setup)...
echo.

set "PY_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
set "PY_ZIP=%TEMP%\python_embedded.zip"
set "PY_DIR=%~dp0python_embeded"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_ZIP%'"

if not exist "%PY_ZIP%" (
    echo [ERROR] Failed to download Python. Check internet connection.
    pause
    exit /b
)

echo [INFO] Extracting to python_embeded\...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Expand-Archive -Path '%PY_ZIP%' -DestinationPath '%PY_DIR%' -Force"
del "%PY_ZIP%" 2>nul

:: Enable pip by uncommenting 'import site' in python312._pth
echo [INFO] Enabling pip support...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Content '%PY_DIR%\python312._pth') -replace '#import site','import site' | Set-Content '%PY_DIR%\python312._pth'"

:: Install pip
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
:: DEPENDENCY INSTALLATION
:: Embedded Python: install directly (no venv support)
:: System Python:   use .venv for isolation
:: ============================================================

:: Clear __pycache__ to avoid stale .pyc on network drives
if exist "Manager\__pycache__" rd /s /q "Manager\__pycache__" >nul 2>&1
if exist "Manager\ui\__pycache__" rd /s /q "Manager\ui\__pycache__" >nul 2>&1
if exist "Manager\core\__pycache__" rd /s /q "Manager\core\__pycache__" >nul 2>&1

if "%USING_EMBEDDED%"=="1" (
    echo [INFO] Installing dependencies into Embedded Python...
    
    "%PYTHON_EXE%" -m pip --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [WARN] pip missing. Bootstrapping...
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'"
        "%PYTHON_EXE%" "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
        del "%TEMP%\get-pip.py" 2>nul
    )
    
    "%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
    "%PYTHON_EXE%" -m pip install PySide6 requests --no-warn-script-location >nul 2>&1
    
    echo [INFO] Launching DSUComfyCG Manager...
    "%PYTHON_EXE%" Manager\main.py
    
) else (
    :: System Python - use venv for isolation
    if not exist ".venv\Scripts\python.exe" (
        echo [INFO] Creating Virtual Environment ^(.venv^)...
        "%PYTHON_EXE%" -m venv .venv
        if %errorlevel% neq 0 (
            echo [ERROR] Failed to create virtual environment.
            pause
            exit /b
        )
    )
    
    echo [INFO] Installing required UI dependencies...
    call .venv\Scripts\activate.bat
    
    python -m pip --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [WARN] pip missing. Bootstrapping...
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'"
        python "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
        del "%TEMP%\get-pip.py" 2>nul
    )
    
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install PySide6 requests --no-warn-script-location >nul 2>&1
    
    echo [INFO] Launching DSUComfyCG Manager...
    python Manager\main.py
    
    deactivate >nul 2>&1
)

if %errorlevel% neq 0 (
    echo.
    echo -------------------------------------------------------------------------
    echo Manager UI crashed or encountered an error.
    echo -------------------------------------------------------------------------
    pause
)
