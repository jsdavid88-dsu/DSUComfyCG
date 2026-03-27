@Echo off&&cd /D %~dp0
Title DSUComfyCG - ComfyUI

:: Setup portable Git PATH
if exist "%~dp0..\git_portable\cmd\git.exe" (
    set "PATH=%~dp0..\git_portable\cmd;%PATH%"
)

:: Set colors ::
set   green=[92m
set  yellow=[93m
set   reset=[0m

:: Resolve Python path: envs/stable first, then root python_embeded
set "PYTHON_EXE="
if exist "%~dp0..\envs\stable\python_embeded\python.exe" (
    set "PYTHON_EXE=%~dp0..\envs\stable\python_embeded\python.exe"
) else if exist "%~dp0python_embeded\python.exe" (
    set "PYTHON_EXE=%~dp0python_embeded\python.exe"
) else (
    echo [ERROR] Python not found. Run DSU_Manager.bat first.
    pause
    exit /b
)

:: Resolve ComfyUI path: envs/stable first, then root
set "COMFY_MAIN="
if exist "%~dp0..\envs\stable\ComfyUI\main.py" (
    set "COMFY_MAIN=%~dp0..\envs\stable\ComfyUI\main.py"
) else if exist "%~dp0ComfyUI\main.py" (
    set "COMFY_MAIN=%~dp0ComfyUI\main.py"
) else (
    echo [ERROR] ComfyUI not found. Run DSU_Manager.bat first.
    pause
    exit /b
)

echo.
echo %green%========================================================%reset%
echo %yellow%   DSUComfyCG - Starting ComfyUI%reset%
echo %green%========================================================%reset%
echo.

:: Scan for new workflows and install dependencies ::
echo %green%::::::::::::::: Scanning Workflows... :::::::::::::::%reset%
"%PYTHON_EXE%" -I scan_and_install.py
echo.

:: Start ComfyUI ::
echo %green%::::::::::::::: Starting ComfyUI :::::::::::::::%reset%
"%PYTHON_EXE%" -I -W ignore::FutureWarning "%COMFY_MAIN%" --windows-standalone-build

pause
