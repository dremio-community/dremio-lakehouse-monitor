@echo off
title Dremio Lakehouse Monitor
echo =========================================
echo Starting Dremio Lakehouse Monitor...
echo =========================================

echo Checking and installing required dependencies...
python -m pip install aiohttp requests

echo.
echo Launching backend server...
echo The dashboard will open in your default browser.
echo Please leave this window open while using the monitor.
echo.

:: Open the browser after a short delay to allow the server to start
start "" http://127.0.0.1:8770

:: Run the python script
python monitor.py --port 8770

pause
