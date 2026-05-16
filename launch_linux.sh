#!/bin/bash
# Navigate to the directory where this script is located
cd "$(dirname "$0")"

echo "========================================="
echo "Starting Dremio Lakehouse Monitor..."
echo "========================================="

echo "Checking and installing required dependencies..."
python3 -m pip install aiohttp requests

echo ""
echo "Launching backend server..."
echo "The dashboard will open in your default browser."
echo "Please leave this terminal window open while using the monitor."
echo ""

# Open the browser after a 2-second delay to allow the server to start
(sleep 2 && xdg-open http://127.0.0.1:8770) &

# Run the python script
python3 monitor.py --port 8770
