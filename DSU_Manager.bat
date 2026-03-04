@echo off
cd /D "%~dp0"
echo Starting DSUComfyCG Manager...

:: Try system python
python Manager\main.py

if %errorlevel% neq 0 (
    echo.
    echo -------------------------------------------------------------------------
    echo Python failed to start Manager. Please ensure Python 3.10+ is installed.
    echo -------------------------------------------------------------------------
    pause
)
