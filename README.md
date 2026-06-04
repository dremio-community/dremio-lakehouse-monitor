# Lakehouse Monitor for Dremio

A real-time observability and dashboarding tool for Apache Iceberg and Dremio environments. 

## Prerequisites
- Python 3.8+
- Network access to Dremio Cloud or a local Dremio Software environment

## Installation (Docker - Recommended)

The easiest way to run the Lakehouse Monitor is via Docker. This ensures a clean environment and automatic persistence of your settings.

```bash
# 1. Build and start the container
docker-compose up -d

# 2. Open your browser to http://localhost:8770
```
*Note: If your Dremio instance is running locally on your machine, use `host.docker.internal` (Mac/Windows) or your machine's IP address instead of `localhost` when configuring the connection in the UI.*

## Installation (Local/Python)

1. Unzip the project folder and navigate to it in your terminal:
   ```bash
   cd dremio-lakehouse-monitor
   ```

2. (Optional but recommended) Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. No external dependencies are required! The application uses pure Python standard libraries.


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

## Core/Standard Monitors
- **Server Status**: Checks the overall health of the Dremio coordinator.
- **Active Jobs**: Tracks currently running queries and jobs (including queued status).
- **Recent Jobs**: Retrieves a list of recently completed jobs.
- **Job Counts**: Aggregates totals for completed and failed queries.
- **Sources**: Monitors the connectivity and health status of all connected data sources.
- **Reflections**: Tracks general reflection configurations and their active/failed statuses.
- **Materializations**: Monitors the underlying materialization updates for reflections.
- **Memory**: Tracks heap and direct memory usage across Dremio nodes.
- **Top Users**: Identifies the most active users by query volume.
- **Top Datasets**: Highlights the most frequently queried datasets.
- **Duration Distribution**: Categorizes queries into different duration buckets to track performance trends.
- **Success Breakdown**: Tracks query success versus failure rates.
- **Query Lifecycle**: Measures the time spent in different query phases (queueing, planning, execution).
- **Error Patterns**: Identifies common query error types and their frequencies.
- **Query Types**: Breaks down query origins (e.g., UI, ODBC/JDBC, REST).
- **Scan Efficiency**: Monitors table scan performance and efficiency metrics.
- **Reflection Efficiency**: Evaluates how effectively reflections are being utilized by the engine.

## Advanced/Enhanced Monitors
- **Engine Health**: Provides a deep dive into engine node count, overall memory pressure, and identifies nodes in warning or critical states.
- **Reflection Health**: Advanced analysis that tracks dead accelerations, wasted storage footprints, and calculates an overall reflection health score.
- **Iceberg Health**: Detailed, table-level health metrics for specifically "watched" Iceberg tables.
- **Thread Info**: Monitors system thread usage and availability.
- **C3 Hit Rates**: Tracks Cloud Column Cache (C3) efficiency and hit rates.
- **WLM Queue Metrics**: Monitors Workload Management queues to identify bottlenecks.
- **Spill to Disk**: Tracks queries that are spilling memory to disk.
- **Catalog Sync Health**: Monitors the health and latency of catalog synchronizations.
- **Iceberg Maintenance**: Tracks the status of Iceberg maintenance operations like optimization and vacuuming.
- **Autoscaling Events**: Logs engine autoscaling activities (scale-ups and scale-downs).

## Schema Drift Monitor

The **Schema Drift Monitor** tracks column-level changes across your watched Iceberg tables over time and alerts you when breaking changes occur.

### How it works

Every 5 minutes the monitor runs `DESCRIBE TABLE` against each watched Iceberg table and snapshots the result to a local SQLite store. Each snapshot is diffed against the previous one to detect:

| Change Type | Description |
|---|---|
| **Column Dropped** | A column present in the previous snapshot is missing |
| **Type Changed** | A column's data type has changed (e.g. `INT` → `BIGINT`) |
| **Nullability Changed** | A column's nullable constraint has changed |
| **Column Added** | A new column has appeared |

Dropped columns and type changes are the most dangerous — they silently break downstream queries, reflections, and BI tools.

### Schema tab

The **🔀 Schema** tab in the UI provides:

- **Summary cards** — tables monitored, total drift events, columns dropped, type changes
- **Drift event log** — color-coded timeline of every detected change with before/after values and an Ack button to mark events as reviewed
- **Current schema viewer** — inspect the latest captured column list for any watched table, with drifted columns highlighted inline
- **Badge** on the tab showing the count of unacknowledged drift events

The tab updates live via WebSocket whenever a new drift is detected during a poll cycle.

### Schema drift alert rule

A new `schema_drift` alert rule type is available in the Alerts tab. When triggered it fires a notification describing what changed (e.g. "2 column(s) dropped, 1 type change(s)") and routes through the same email/webhook channels as other alerts. Set severity to **Critical** for dropped columns if downstream breakage is a concern.

### Data retention

Schema snapshots are retained for 90 days per table. Drift events persist indefinitely until acknowledged.

## Built-in Alerting Engine
The Dremio Lakehouse Monitor features a built-in alerting engine that evaluates polled metrics against custom thresholds.
Here is a breakdown of what the alerting system currently supports:

### Alerting Rule Types (Conditions)
1. **Query Duration**: Triggers if any active query has been running longer than a specified threshold (in minutes).
2. **Memory Pressure**: Triggers if the heap memory usage on any individual Dremio node exceeds a defined percentage (e.g., > 90%).
3. **Queue Depth**: Triggers if the number of queries stuck in an "ENQUEUED" state meets or exceeds your threshold, indicating potential engine bottlenecks.
4. **Source Down**: Triggers immediately if any connected data source loses connectivity or enters an unhealthy state.
5. **Reflection Failures**: Triggers if the count of reflections in a "FAILED" state hits your threshold limit.
6. **Failed Jobs**: Triggers if the total count of failed queries/jobs exceeds a certain limit.
7. **Schema Drift**: Triggers whenever a column is dropped, a type changes, or a column is added on any watched Iceberg table.

### Alert Features
- **Severity Levels**: Alerts can be categorized as Info, Warning, or Critical.
- **Cooldown Periods**: You can set cooldown timers (in minutes) per rule to prevent alert spam if a condition persists.
- **Granular Toggles**: Rules can be individually enabled or disabled.

### Notification Channels
The alerting engine currently supports pushing notifications out through two main channels:
1. **Email (SMTP)**: Sends HTML-formatted emails. It supports standard SMTP configurations, including custom ports, SSL/TLS, and authentication.
2. **Webhooks**: Sends formatted JSON payloads suitable for platforms like Slack, Microsoft Teams, Discord, or PagerDuty. The payloads automatically format text, colors, and emojis based on the alert's severity level.
