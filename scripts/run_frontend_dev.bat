@echo off
setlocal
cd /d "%~dp0\..\frontend"

echo Starting Vite development server on port 5173 ...
npm run dev
pause
