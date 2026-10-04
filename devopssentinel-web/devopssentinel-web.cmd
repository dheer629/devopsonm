@echo off
rem DevOpsSentinel Web -- Windows launcher.
rem
rem The engine, kubectl and kubeconfig live inside WSL, so this wrapper starts
rem the app in WSL and lets the launcher open the Windows browser. WSL2
rem forwards 127.0.0.1, so Chrome on Windows reaches the local server.
rem
rem Usage:  devopssentinel-web.cmd [--open] [--no-open] [--debug] [--incident ID]
rem                                [--context NAME] [--namespace NAME] [--port N]
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not defined DSWEB_WSL_DISTRO set "DSWEB_WSL_DISTRO=Ubuntu"

rem Forward every argument to the bash launcher.
set "ARGS="
:parse
if "%~1"=="" goto run
set "ARGS=%ARGS% %1"
shift
goto parse

:run
where wsl.exe >nul 2>&1
if errorlevel 1 (
    echo WSL was not found. Install WSL2 with an Ubuntu distribution, or run
    echo ./devopssentinel-web directly from a Linux shell.
    exit /b 3
)

echo Starting DevOpsSentinel Web in WSL (%DSWEB_WSL_DISTRO%)...
echo Workspace: %ROOT%

rem Normalise CRLF in the launcher/scripts (harmless if already LF), then run.
wsl.exe -d %DSWEB_WSL_DISTRO% -- bash -lc "cd \"$(wslpath -a '%ROOT%')\" && sed -i 's/\r$//' devopssentinel-web scripts/*.sh && exec bash devopssentinel-web%ARGS%"
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
