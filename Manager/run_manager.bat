@Echo off&&cd /D %~dp0
Title DSUComfyCG Manager

:: Navigate to parent (DSUComfyCG folder)
cd ..

:: Setup portable Git PATH
if exist "%~dp0..\git_portable\cmd\git.exe" (
    set "PATH=%~dp0..\git_portable\cmd;%PATH%"
)

:: Check and install dependencies
.\python_embeded\python.exe -c "import PySide6" 2>nul
if errorlevel 1 (
    echo Installing PySide6...
    .\python_embeded\python.exe -m pip install PySide6 --quiet
)

.\python_embeded\python.exe -c "import requests" 2>nul
if errorlevel 1 (
    echo Installing requests...
    .\python_embeded\python.exe -m pip install requests --quiet
)

:: Run Manager
.\python_embeded\python.exe -I Manager\main.py

pause
