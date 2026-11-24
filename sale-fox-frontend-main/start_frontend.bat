@echo off
cd /d "%~dp0"
title SaleFox - Frontend UI
echo ========================================================
echo Starting SaleFox React Frontend on Port 5173...
echo ========================================================
if not exist node_modules call npm install
npm run dev -- --host 0.0.0.0 --port 5173
pause
