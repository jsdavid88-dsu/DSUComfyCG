@Echo off&&cd /D %~dp0
Title DSUComfyCG - ComfyUI

:: Set colors ::
set   green=[92m
set  yellow=[93m
set   reset=[0m

echo.
echo %green%========================================================%reset%
echo %yellow%   DSUComfyCG - Starting ComfyUI%reset%
echo %green%========================================================%reset%
echo.

:: Scan for new workflows and install dependencies ::
echo %green%::::::::::::::: Scanning Workflows... :::::::::::::::%reset%
.\python_embeded\python.exe -I scan_and_install.py
echo.

:: Start ComfyUI ::
echo %green%::::::::::::::: Starting ComfyUI :::::::::::::::%reset%
.\python_embeded\python.exe -I -W ignore::FutureWarning ComfyUI\main.py --windows-standalone-build

pause
