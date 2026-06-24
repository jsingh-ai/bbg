@echo off
setlocal
cd /d "%~dp0\.."

if not exist .env (
    echo Missing .env file. Copy .env.example to .env and edit it first.
    pause
    exit /b 1
)

if not exist .venv\Scripts\python.exe (
    echo Missing Python virtual environment. Run scripts\install_backend.bat first.
    pause
    exit /b 1
)

echo Starting BBG OPC Dashboard on port 8000 ...
call .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
pause
