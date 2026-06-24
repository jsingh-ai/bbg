@echo off
setlocal
cd /d "%~dp0\.."

echo Creating Python virtual environment in .venv ...
py -3 -m venv .venv
if errorlevel 1 (
    echo Failed to create venv. Make sure Python 3.11+ is installed and available as py.
    pause
    exit /b 1
)

echo Upgrading pip ...
call .venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 exit /b 1

echo Installing backend Python packages ...
call .venv\Scripts\pip.exe install -r backend\requirements.txt
if errorlevel 1 exit /b 1

echo Backend install complete.
pause
