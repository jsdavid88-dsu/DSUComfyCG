@Echo off&&cd /D %~dp0
Title DSUComfyCG Manager

:: Navigate to parent (DSUComfyCG folder)
cd ..

:: Check if PySide6 is installed
.\python_embeded\python.exe -c "import PySide6" 2>nul
if errorlevel 1 (
    echo Installing PySide6...
    .\python_embeded\python.exe -m pip install PySide6 --quiet
)

:: Run Manager
.\python_embeded\python.exe -I Manager\main.py

pause
