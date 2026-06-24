@echo off
setlocal
cd /d "%~dp0\..\frontend"

echo Building React frontend ...
npm run build
if errorlevel 1 (
    echo Frontend build failed.
    pause
    exit /b 1
)

echo Frontend build complete. FastAPI will serve frontend\dist after restart.
pause
