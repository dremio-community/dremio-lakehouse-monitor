# Lakehouse Monitor for Dremio

A real-time observability and dashboarding tool for Apache Iceberg and Dremio environments. 

## Prerequisites
- Python 3.8+
- Network access to Dremio Cloud or a local Dremio Software environment

## Installation

1. Unzip the project folder and navigate to it in your terminal:
   ```bash
   cd dremio-lakehouse-monitor
   ```

2. (Optional but recommended) Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install the required Python dependencies:
   ```bash
   pip install aiohttp requests
   ```

## Running the Monitor

The easiest way to run the monitor is to use the **clickable launchers** provided for your operating system. These scripts will automatically install required dependencies, start the backend server, and open your web browser directly to the dashboard.

- **Mac**: Double-click `launch_mac.command` (and `stop_mac.command` to stop)
- **Windows**: Double-click `launch_windows.bat` (and `stop_windows.bat` to stop)
- **Linux**: Run or double-click `Start Dremio Monitor.desktop` (and `Stop Dremio Monitor.desktop` to stop)

Alternatively, you can start the backend server manually via the terminal by running the `monitor.py` script. You can specify a custom port with `--port`.

```bash
python3 monitor.py --port 8770
```

## Setup & Configuration

1. Open your web browser and navigate to `http://127.0.0.1:8770`.
2. On the first launch, you will be presented with a **Setup** screen.
3. Check the **Dremio Cloud** box if you are connecting to Dremio Cloud, and enter your **Project ID** and **Personal Access Token (PAT)**. 
   *(If connecting to a local Dremio environment, uncheck the box and enter your Dremio hostname, port, and credentials).*
4. Click **Connect**.
5. Once connected, navigate to the **Settings** tab to select which Apache Iceberg tables you want to actively monitor for snapshot counts and file sizes!

## Architecture Note
This is a lightweight application. The backend is powered by Python's `http.server` and uses a local SQLite database (`monitor.db`) to store your active connection profile, widget layouts, and selected tables. The frontend streams data dynamically via WebSocket.

## Advanced Observability Features
The dashboard includes advanced observability monitors specifically built for Dremio and Iceberg:
- **C3 Hit Rates**: Monitor columnar cloud cache hit vs. miss rates.
- **WLM Queue Metrics**: Track queue concurrency, wait times, and rejections.
- **Spill-to-Disk Tracking**: Monitor queries exhausting memory allocations.
- **Catalog Sync Health**: Track metadata sync latencies for external sources.
- **Iceberg Maintenance**: Monitor OPTIMIZE, VACUUM, and ROLLBACK jobs.
- **Auto-Scaling Events**: Track engine scaling for Dremio Cloud.
