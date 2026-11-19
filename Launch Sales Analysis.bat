@echo off
setlocal
cd /d "%~dp0"
title Sales Analysis - Launcher

REM ---- 1. Make sure Docker is running (start Docker Desktop if needed) ----
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

echo Docker is not running - starting Docker Desktop...
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:wait_docker
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a tries+=1
if %tries% GEQ 60 goto docker_fail
goto wait_docker

:docker_fail
echo.
echo Docker did not start. Please install/open Docker Desktop and try again.
pause
exit /b 1

REM ---- 2. Build (cached after the first time) and start the container ----
:docker_ready
if not exist data mkdir data
echo Building / starting the app. The first run takes a few minutes...
docker compose up -d --build
if errorlevel 1 goto compose_fail

REM ---- 3. Wait until the web viewer answers, then open the browser ----
set /a tries=0
:wait_app
curl -s -o nul http://localhost:6080/vnc.html
if not errorlevel 1 goto open_browser
timeout /t 1 /nobreak >nul
set /a tries+=1
if %tries% GEQ 60 goto compose_fail
goto wait_app

:open_browser
start "" "http://localhost:6080/vnc.html?autoconnect=true&resize=scale&reconnect=true"
exit /b 0

:compose_fail
echo.
echo Something went wrong. Last log lines:
docker compose logs --tail 40
pause
exit /b 1
