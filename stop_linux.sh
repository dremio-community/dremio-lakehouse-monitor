#!/bin/bash
echo "========================================="
echo "Stopping Dremio Lakehouse Monitor..."
echo "========================================="

# Find and kill the python process running monitor.py
pkill -f "python3 monitor.py"
pkill -f "python monitor.py"

echo "Monitor stopped successfully."
sleep 2
