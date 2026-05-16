@echo off
title Stop Dremio Lakehouse Monitor
echo =========================================
echo Stopping Dremio Lakehouse Monitor...
echo =========================================

:: Find and kill the python process running monitor.py
wmic process where "name='python.exe' and CommandLine like '%%monitor.py%%'" call terminate >nul 2>&1
wmic process where "name='python3.exe' and CommandLine like '%%monitor.py%%'" call terminate >nul 2>&1

echo Monitor stopped successfully.
pause
