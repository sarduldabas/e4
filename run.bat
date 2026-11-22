@echo off
rem Double-click to install (first time only) and start all three services, then open the app.
cd /d "%~dp0"

where python >nul 2>nul || (echo Python was not found. Install Python 3.12+ and try again. & pause & exit /b 1)
where npm >nul 2>nul || (echo Node.js/npm was not found. Install Node 20+ and try again. & pause & exit /b 1)

rem Installing is safe to repeat: when everything is already installed it only takes a few seconds,
rem and it picks up new packages after an update.
echo Installing / checking packages (first time takes a few minutes)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" -Install
if errorlevel 1 (echo Install failed. See messages above. & pause & exit /b 1)

:start
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1"
echo Waiting for the services to start...
timeout /t 12 /nobreak >nul
start "" http://localhost:5173
echo.
echo Three windows are running (agents, backend, front end). Close them to stop.
pause
