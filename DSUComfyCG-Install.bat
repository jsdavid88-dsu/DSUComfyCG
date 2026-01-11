@Echo off&&cd /D %~dp0
Title DSUComfyCG Installer v1.0.0 by Dongseo University
:: DSUComfyCG - ComfyUI Easy Installer for CG Education ::

:: Set the Python version ::
set "PYTHON_VERSION=3.12"
set "PYTHON_VER=3.12.10"

:: Set colors ::
set warning=[33m
set     red=[91m
set   green=[92m
set  yellow=[93m
set    bold=[1m
set   reset=[0m

:: Set arguments ::
set "PIPargs=--no-cache-dir --no-warn-script-location --timeout=1000 --retries 200"
set "CURLargs=--retry 200 --retry-all-errors"
set "UVargs=--no-cache --link-mode=copy"

:: Set local path ::
for /f "delims=" %%G in ('cmd /c "where git.exe 2>nul"') do (set "GIT_PATH=%%~dpG")
set path=%GIT_PATH%
if exist %windir%\System32 set path=%PATH%;%windir%\System32
if exist %windir%\System32\WindowsPowerShell\v1.0 set path=%PATH%;%windir%\System32\WindowsPowerShell\v1.0
if exist %localappdata%\Microsoft\WindowsApps set path=%PATH%;%localappdata%\Microsoft\WindowsApps

:: Check for Existing DSUComfyCG Folder ::
if exist DSUComfyCG (
    echo %warning%WARNING:%reset% '%bold%DSUComfyCG%reset%' folder already exists!
    echo %green%Move this file to another folder and run it again.%reset%
    echo Press any key to Exit...&Pause>nul
    goto :eof
)

echo.
echo %green%========================================================%reset%
echo %yellow%   DSUComfyCG - One-Click ComfyUI Installer%reset%
echo %green%   Dongseo University CG Education Edition%reset%
echo %green%========================================================%reset%
echo.

:: Capture the start time ::
for /f "delims=" %%i in ('powershell -command "Get-Date -Format yyyy-MM-dd_HH:mm:ss"') do set start=%%i

:: Install/Update Git ::
call :install_git

:: Check if git is installed ::
for /F "tokens=*" %%g in ('git --version') do (set gitversion=%%g)
Echo %gitversion% | findstr /C:"version">nul&&(
    Echo %bold%git%reset% %yellow%is installed%reset%
    Echo.) || (
    Echo %warning%WARNING:%reset% %bold%'git'%reset% is NOT installed
    Echo Please install %bold%'git'%reset% manually from %yellow%https://git-scm.com/%reset% and run this installer again
    Echo Press any key to Exit...&Pause>nul
    exit /b
)

:: Create main folder ::
md DSUComfyCG
if not exist DSUComfyCG (
    echo %warning%WARNING:%reset% Cannot create folder %yellow%DSUComfyCG%reset%
    echo Make sure you are NOT using system folders like %yellow%Program Files, Windows%reset%
    echo Press any key to Exit...&Pause>nul
    exit /b
)
cd DSUComfyCG

:: Install ComfyUI ::
call :install_comfyui

:: Install Core Nodes ::
echo %green%::::::::::::::: Installing %yellow%Core Custom Nodes%green% :::::::::::::::%reset%
echo.
call :get_node https://github.com/Comfy-Org/ComfyUI-Manager                ComfyUI-Manager
call :get_node https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite     ComfyUI-VideoHelperSuite
call :get_node https://github.com/cubiq/ComfyUI_IPAdapter_plus             ComfyUI_IPAdapter_plus
call :get_node https://github.com/Fannovel16/comfyui_controlnet_aux        comfyui_controlnet_aux
call :get_node https://github.com/Lightricks/ComfyUI-LTXVideo              ComfyUI-LTXVideo
call :get_node https://github.com/kijai/ComfyUI-WanVideoWrapper            ComfyUI-WanVideoWrapper

:: Copy Helper files ::
echo %green%::::::::::::::: Copying %yellow%Helper Files%green% :::::::::::::::%reset%
if exist ..\Helper\run_comfy.bat copy ..\Helper\run_comfy.bat .\>nul
if exist ..\Helper\scan_and_install.py copy ..\Helper\scan_and_install.py .\>nul
if exist ..\workflows xcopy ..\workflows workflows\ /E /Y /I /Q>nul

:: Create workflows folder if not exists ::
if not exist workflows md workflows

:: Capture the end time ::
for /f "delims=" %%i in ('powershell -command "Get-Date -Format yyyy-MM-dd_HH:mm:ss"') do set end=%%i
for /f "delims=" %%i in ('powershell -command "$s=[datetime]::ParseExact('%start%','yyyy-MM-dd_HH:mm:ss',$null); $e=[datetime]::ParseExact('%end%','yyyy-MM-dd_HH:mm:ss',$null); if($e -lt $s){$e=$e.AddDays(1)}; ($e-$s).TotalSeconds"') do set diff=%%i

:: Final Messages ::
echo.
echo %green%::::::::::::::: Installation Complete :::::::::::::::%reset%
echo %green%::::::::::::::: Total Running Time:%red% %diff% %green%seconds%reset%
echo.
echo %yellow%To start ComfyUI, run:%reset% %bold%run_comfy.bat%reset%
echo.
echo %yellow%::::::::::::::: Press any key to exit :::::::::::::::%reset%&Pause>nul
goto :eof

::::::::::::::::::::::::::::::::: FUNCTIONS :::::::::::::::::::::::::::::::::

:install_git
:: https://git-scm.com/
echo %green%::::::::::::::: Checking/Installing%yellow% Git %green%:::::::::::::::%reset%
echo.
winget.exe install --id Git.Git -e --source winget
set path=%PATH%;%ProgramFiles%\Git\cmd
echo.
goto :eof

:install_comfyui
:: https://github.com/comfyanonymous/ComfyUI
echo %green%::::::::::::::: Installing%yellow% ComfyUI %green%:::::::::::::::%reset%
echo.
git.exe clone https://github.com/comfyanonymous/ComfyUI ComfyUI

:: Download Portable Python ::
echo %green%::::::::::::::: Installing%yellow% Portable Python %PYTHON_VER% %green%:::::::::::::::%reset%
md python_embeded&&cd python_embeded
curl.exe -OL https://www.python.org/ftp/python/%PYTHON_VER%/python-%PYTHON_VER%-embed-amd64.zip --ssl-no-revoke %CURLargs%
tar.exe -xf python-%PYTHON_VER%-embed-amd64.zip
erase python-%PYTHON_VER%-embed-amd64.zip
curl.exe -sSL https://bootstrap.pypa.io/get-pip.py -o get-pip.py --ssl-no-revoke %CURLargs%

:: Configure Python path ::
Echo ../ComfyUI> python312._pth
Echo python312.zip>> python312._pth
Echo .>> python312._pth
Echo Lib/site-packages>> python312._pth
Echo Lib>> python312._pth
Echo Scripts>> python312._pth
Echo # import site>> python312._pth

:: Install pip, uv, PyTorch ::
echo %green%::::::::::::::: Installing%yellow% pip, uv, PyTorch %green%:::::::::::::::%reset%
.\python.exe -I get-pip.py %PIPargs%
.\python.exe -I -m pip install uv %PIPargs%
.\python.exe -I -m pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128 %PIPargs%
.\python.exe -I -m uv pip install pygit2 %UVargs%

:: Install ComfyUI requirements ::
cd ..\ComfyUI
..\python_embeded\python.exe -I -m uv pip install -r requirements.txt %UVargs%
cd ..\
echo.
goto :eof

:get_node
set git_url=%~1
set git_folder=%~2
echo %green%::::::::::::::: Installing%yellow% %git_folder% %green%:::::::::::::::%reset%
echo.
git.exe clone --depth 1 %git_url% ComfyUI/custom_nodes/%git_folder%

:: Install node requirements if exists ::
setlocal enabledelayedexpansion
if exist ".\ComfyUI\custom_nodes\%git_folder%\requirements.txt" (
    for %%F in (".\ComfyUI\custom_nodes\%git_folder%\requirements.txt") do set filesize=%%~zF
    if not !filesize! equ 0 (
        .\python_embeded\python.exe -I -m uv pip install -r ".\ComfyUI\custom_nodes\%git_folder%\requirements.txt" %UVargs%
    )
)
:: Run install.py if exists ::
if exist .\ComfyUI\custom_nodes\%git_folder%\install.py (
    for %%F in (".\ComfyUI\custom_nodes\%git_folder%\install.py") do set filesize=%%~zF
    if not !filesize! equ 0 (
        .\python_embeded\python.exe -I .\ComfyUI\custom_nodes\%git_folder%\install.py
    )
)
endlocal
echo.
goto :eof
