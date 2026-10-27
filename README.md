**Lakehouse Monitor for Dremio**

A real-time observability and dashboarding tool for Apache Iceberg and Dremio environments.

Prerequisites
Python 3.8+
Network access to Dremio Cloud or a local Dremio Software environment
Installation (Docker - Recommended)

The easiest way to run the Lakehouse Monitor is via Docker. This ensures a clean environment and automatic persistence of your settings.

bash
# 1. Build and start the container
docker-compose up -d
# 2. Open your browser to http://localhost:8770

Note: If your Dremio instance is running locally on your machine, use host.docker.internal (Mac/Windows) or your machine's IP address instead of localhost when configuring the connection in the UI.

**Installation (Local/Python)**

Unzip the project folder and navigate to it in your terminal:

bash
cd dremio-lakehouse-monitor

(Optional but recommended) Create a virtual environment:

bash
python3 -m venv venv
source venv/bin/activate

No external dependencies are required! The application uses pure Python standard libraries.

**Running the Monitor**

The easiest way to run the monitor is to use the clickable launchers provided for your operating system. These scripts will automatically install required dependencies, start the backend server, and open your web browser directly to the dashboard.

Mac: Double-click launch_mac.command (and stop_mac.command to stop)
Windows: Double-click launch_windows.bat (and stop_windows.bat to stop)
Linux: Run or double-click Start Dremio Monitor.desktop (and Stop Dremio Monitor.desktop to stop)

Alternatively, you can start the backend server manually via the terminal by running the monitor.py script. You can specify a custom port with --port.

bash
python3 monitor.py --port 8770
Setup & Configuration
Open your web browser and navigate to http://127.0.0.1:8770.
On the first launch, you will be presented with a Setup screen.
Check the Dremio Cloud box if you are connecting to Dremio Cloud, and enter your Project ID and Personal Access Token (PAT). (If connecting to a local Dremio environment, uncheck the box and enter your Dremio hostname, port, and credentials).
Click Connect.
Once connected, navigate to the Settings tab to select which Apache Iceberg tables you want to actively monitor for snapshot counts and file sizes!

**Architecture Note**

This is a lightweight, self-contained application. The backend is powered by Python's http.server and uses a local SQLite database (monitor.db) to store your active connection profile, widget layouts, alert rules, and rolling metric snapshots. The frontend streams data dynamically via WebSocket.

**Required Dremio Permissions**

The Lakehouse Monitor is strictly read-only—it never modifies datasets, reflections, sources, or cluster settings. However, because it queries system tables and cluster metadata, the configured Dremio user or Personal Access Token (PAT) requires specific permissions depending on your deployment type.

1. Dremio Software (Self-Managed)
Recommended Role: ADMIN (or a dedicated monitoring service account granted explicit SELECT access to system tables).
Why? In Dremio Software, non-admin users querying sys.jobs or sys.jobs_recent only see their own queries, and cannot access cluster-wide tables like sys.reflections, sys.memory, or the /api/v3/source API endpoint.

REST API Endpoints Accessed:
POST /apiv2/login (Authentication token exchange when using username/password)
GET /apiv2/server_status (Coordinator health check)
GET /api/v3/source (Source connectivity and health states)
POST /api/v3/sql, GET /api/v3/job/{id}, GET /api/v3/job/{id}/results (Executing read-only monitoring queries)
System Views & Tables Queried (SELECT):
sys.jobs & sys.jobs_recent (Active queries, WLM queue metrics, lifecycle phases, top users/datasets, error patterns, scan efficiency)
sys.reflections & sys.materializations (Reflection health, utilization, storage footprint, and refresh history)
sys.memory & sys.threads (Node-level heap/direct memory pressure and thread pool metrics)
sys.sources (Catalog sync health)
INFORMATION_SCHEMA."TABLES" (Listing available tables for the Iceberg table watcher)
Watched Iceberg Tables (Optional):
Requires SELECT privilege on any specific Apache Iceberg table added to the Watch List in order to query TABLE(table_snapshot('<table_path>')) and TABLE(table_files('<table_path>')).

**3. Dremio Cloud**

Required Privileges:

USAGE privilege on the target Project and the default Compute Engine used to run monitoring SQL queries.
Access to project system tables (sys.project.history.jobs and sys.project.reflections), typically available to Project Admins or roles granted system table visibility.
SELECT privilege on any specific Apache Iceberg tables added to the Iceberg Health Watch List.
REST API Endpoints Accessed:
GET /v0/projects/{project_id}/source (Health check and source status)
GET /v0/projects/{project_id}/engines (Engine status and autoscaling monitoring)
POST /v0/projects/{project_id}/sql, GET /v0/projects/{project_id}/job/{id}, GET /v0/projects/{project_id}/job/{id}/results
System Views & Tables Queried (SELECT):
sys.project.history.jobs
sys.project.reflections
INFORMATION_SCHEMA."TABLES"
TABLE(table_snapshot('<table_path>')) & TABLE(table_files('<table_path>')) (for watched Iceberg tables)
How Monitoring Data is Stored

All persistent state is stored locally in a single embedded SQLite database file (running in WAL mode). No telemetry or monitoring data is sent to any external service unless you explicitly configure Email (SMTP) or Webhook alerting.

**Storage Location**
Local / Python Execution: Stored at ./monitor.db in the project root directory.
Docker Execution: Stored at /data/monitor.db inside the container, persisted via the monitor-data Docker volume defined in docker-compose.yml.

Custom Path: Can be overridden at runtime by setting the DB_PATH environment variable.
What is Stored in Memory vs. On Disk

In-Memory Only (Never Written to Disk):

Live query lists (active_jobs, recent_jobs), raw SQL query text, user names (top_users), dataset names (top_datasets), error messages (error_patterns), and individual node memory details (memory) are held strictly in the Python server's memory (Poller.state) and pushed directly to connected browsers over WebSockets.

Rolling Time-Series Snapshots (24-Hour Automatic Retention):

To power trend charts without unbounded disk growth, the poller writes aggregate numeric counters to SQLite and automatically deletes rows older than 24 hours (86,400 seconds) on every insert:
query_snapshots: Timestamp, active/queued/completed/failed counts, and average duration (polled every 5s).
engine_snapshots: Timestamp, node count, aggregate heap used/max, memory pressure %, and health score (polled every 15s).
reflection_snapshots: Timestamp, total/active/failed/dead reflection counts, health score, average refresh duration, and total/wasted footprint bytes (polled every 60s).

**Alert History (Capped at 1,000 Events):**

alert_history: Stores triggered alert events (rule name, severity, message, JSON details, timestamps, and acknowledgment status). Automatically pruned on insert to retain only the most recent 1,000 alerts.

Configuration & Metadata (Persisted Until Modified/Deleted):

connection_profiles: Dremio host, port, project ID, and authentication credentials.
watched_tables: Table paths selected for Iceberg health checks and their most recent summary JSON (last_health).
alert_rules & notification_config: Custom alert thresholds and SMTP/Webhook settings.
dashboard_layout: UI widget visibility preferences.

Security Considerations for Evaluators

Credential Storage: Connection credentials (passwords or PATs) and SMTP/Webhook configurations are stored in monitor.db so the background poller can authenticate across restarts. While the /api/connections HTTP endpoint masks passwords and tokens (••••••••) when returning profiles to the UI, the underlying monitor.db file contains them in plaintext. Restrict filesystem permissions on monitor.db (e.g., chmod 600 monitor.db) or the Docker volume accordingly.

Network Binding: When running locally via monitor.py, the server binds to 127.0.0.1 by default. In Docker (--host 0.0.0.0), the web UI does not enforce its own login layer; if deploying on a shared network, place the container behind an authenticated reverse proxy or restrict port 8770 via firewall rules.

Core/Standard Monitors

Server Status: Checks the overall health of the Dremio coordinator.
Active Jobs: Tracks currently running queries and jobs (including queued status).
Recent Jobs: Retrieves a list of recently completed jobs.
Job Counts: Aggregates totals for completed and failed queries.
Sources: Monitors the connectivity and health status of all connected data sources.
Reflections: Tracks general reflection configurations and their active/failed statuses.
Materializations: Monitors the underlying materialization updates for reflections.
Memory: Tracks heap and direct memory usage across Dremio nodes.
Top Users: Identifies the most active users by query volume.
Top Datasets: Highlights the most frequently queried datasets.
Duration Distribution: Categorizes queries into different duration buckets to track performance trends.
Success Breakdown: Tracks query success versus failure rates.
Query Lifecycle: Measures the time spent in different query phases (queueing, planning, execution).
Error Patterns: Identifies common query error types and their frequencies.
Query Types: Breaks down query origins (e.g., UI, ODBC/JDBC, REST).
Scan Efficiency: Monitors table scan performance and efficiency metrics.
Reflection Efficiency: Evaluates how effectively reflections are being utilized by the engine.
Advanced/Enhanced Monitors
Engine Health: Provides a deep dive into engine node count, overall memory pressure, and identifies nodes in warning or critical states.
Reflection Health: Advanced analysis that tracks dead accelerations, wasted storage footprints, and calculates an overall reflection health score.
Iceberg Health: Detailed, table-level health metrics for specifically "watched" Iceberg tables.
Thread Info: Monitors system thread usage and availability.
C3 Hit Rates: Tracks Cloud Column Cache (C3) efficiency and hit rates.
WLM Queue Metrics: Monitors Workload Management queues to identify bottlenecks.
Spill to Disk: Tracks queries that are spilling memory to disk.
Catalog Sync Health: Monitors the health and latency of catalog synchronizations.
Iceberg Maintenance: Tracks the status of Iceberg maintenance operations like optimization and vacuuming.
Autoscaling Events: Logs engine autoscaling activities (scale-ups and scale-downs).
Built-in Alerting Engine

The Dremio Lakehouse Monitor features a built-in alerting engine that evaluates polled metrics against custom thresholds. Here is a breakdown of what the alerting system currently supports:

Alerting Rule Types (Conditions)

Query Duration: Triggers if any active query has been running longer than a specified threshold (in minutes).
Memory Pressure: Triggers if the heap memory usage on any individual Dremio node exceeds a defined percentage (e.g., > 90%).
Queue Depth: Triggers if the number of queries stuck in an "ENQUEUED" state meets or exceeds your threshold, indicating potential engine bottlenecks.
Source Down: Triggers immediately if any connected data source loses connectivity or enters an unhealthy state.
Reflection Failures: Triggers if the count of reflections in a "FAILED" state hits your threshold limit.
Failed Jobs: Triggers if the total count of failed queries/jobs exceeds a certain limit.

Alert Features

Severity Levels: Alerts can be categorized as Info, Warning, or Critical.
Cooldown Periods: You can set cooldown timers (in minutes) per rule to prevent alert spam if a condition persists.
Granular Toggles: Rules can be individually enabled or disabled.

Notification Channels

The alerting engine currently supports pushing notifications out through two main channels:

Email (SMTP): Sends HTML-formatted emails. It supports standard SMTP configurations, including custom ports, SSL/TLS, and authentication.
Webhooks: Sends formatted JSON payloads suitable for platforms like Slack, Microsoft Teams, Discord, or PagerDuty. The payloads automatically format text, colors, and emojis based on the alert's severity level.
