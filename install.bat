@echo off
rem FAST-HIPPOS: installation from this folder, for developers and for testing. Users install with
rem FAST-HIPPOS-Setup.exe, which runs the same steps (installer\install.py) with a normal setup window.
rem Run it again to update. Options are passed on, for example:
rem     install.bat --cellpose 3
setlocal
set "HERE=%~dp0"
if not defined FAST_HIPPOS_INSTALL_DIR set "FAST_HIPPOS_INSTALL_DIR=%LOCALAPPDATA%\FAST-HIPPOS"
set "TARGET=%FAST_HIPPOS_INSTALL_DIR%"
echo.
echo  FAST-HIPPOS will be installed in %TARGET%
echo.
set "UV=%TARGET%\bin\uv.exe"
if not exist "%UV%" (
    echo  Fetching uv ^(a small tool that installs Python and the packages^)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:UV_INSTALL_DIR='%TARGET%\bin'; $env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 goto :failed
)
set "UV_PYTHON_INSTALL_DIR=%TARGET%\python"
set "UV_CACHE_DIR=%TARGET%\cache"
"%UV%" run --no-project --python 3.12 "%HERE%installer\install.py" --target "%TARGET%" --uv "%UV%" --shortcut --desktop %*
if errorlevel 1 goto :failed
if "%~1"=="" pause
exit /b 0

:failed
echo.
echo  The installation did not finish. The messages above say what went wrong.
if "%~1"=="" pause
exit /b 1
