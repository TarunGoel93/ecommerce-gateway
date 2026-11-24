@echo off
cd /d "%~dp0"
title SaleFox - Unified Scraper API
echo ========================================================
echo Starting the shared Sale-Fox scraper API on Port 5050...
echo ========================================================
python run_all_backends.py
pause
