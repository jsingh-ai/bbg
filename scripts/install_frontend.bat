@echo off
setlocal
cd /d "%~dp0\..\frontend"

echo Installing frontend packages with npm ...
npm install
if errorlevel 1 (
    echo npm install failed. Make sure Node.js LTS is installed.
    pause
    exit /b 1
)

echo Frontend install complete.
pause
