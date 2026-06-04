"""
SQLite persistence for Dremio Lakehouse Monitor.
Stores alert rules, alert history, query snapshots, and connection profiles.
"""

import sqlite3
import json
import os
import time
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "monitor.db")


def get_db_path():
    return DB_PATH


@contextmanager
def get_connection():
    """Thread-safe database connection context manager."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS connection_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                host TEXT NOT NULL DEFAULT 'localhost',
                port INTEGER NOT NULL DEFAULT 9047,
                auth_type TEXT NOT NULL DEFAULT 'password',  -- 'password' or 'pat'
                username TEXT,
                password TEXT,
                pat_token TEXT,
                is_cloud INTEGER NOT NULL DEFAULT 0,
                cloud_project_id TEXT,
                use_ssl INTEGER NOT NULL DEFAULT 0,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                -- rule_type: 'query_duration', 'failed_jobs', 'reflection_failure',
                --            'memory_pressure', 'source_down', 'queue_depth'
                threshold_value REAL NOT NULL,
                threshold_unit TEXT,  -- 'minutes', 'count', 'percent'
                window_minutes INTEGER DEFAULT 5,
                cooldown_minutes INTEGER DEFAULT 15,
                severity TEXT NOT NULL DEFAULT 'warning',  -- 'info', 'warning', 'critical'
                enabled INTEGER NOT NULL DEFAULT 1,
                notify_email INTEGER NOT NULL DEFAULT 0,
                notify_webhook INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER,
                rule_name TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT,  -- JSON
                acknowledged INTEGER NOT NULL DEFAULT 0,
                triggered_at REAL NOT NULL,
                acknowledged_at REAL,
                FOREIGN KEY (rule_id) REFERENCES alert_rules(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS query_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                active_count INTEGER NOT NULL DEFAULT 0,
                queued_count INTEGER NOT NULL DEFAULT 0,
                completed_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                avg_duration_ms REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS notification_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT UNIQUE NOT NULL,  -- 'email' or 'webhook'
                config TEXT NOT NULL,  -- JSON
                enabled INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_alert_history_triggered
                ON alert_history(triggered_at DESC);
            CREATE INDEX IF NOT EXISTS idx_query_snapshots_timestamp
                ON query_snapshots(timestamp DESC);

            CREATE TABLE IF NOT EXISTS dashboard_layout (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                layout TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS engine_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                node_count INTEGER NOT NULL DEFAULT 0,
                overall_pressure REAL DEFAULT 0,
                total_heap_used INTEGER DEFAULT 0,
                total_heap_max INTEGER DEFAULT 0,
                health_score INTEGER DEFAULT 100,
                critical_nodes INTEGER DEFAULT 0,
                warning_nodes INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS reflection_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                total_reflections INTEGER DEFAULT 0,
                active_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                dead_accel_count INTEGER DEFAULT 0,
                health_score INTEGER DEFAULT 100,
                avg_refresh_ms REAL DEFAULT 0,
                total_footprint_bytes INTEGER DEFAULT 0,
                wasted_bytes INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS watched_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_path TEXT UNIQUE NOT NULL,
                label TEXT,
                added_at REAL NOT NULL,
                last_checked REAL DEFAULT 0,
                last_health TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_engine_snapshots_ts
                ON engine_snapshots(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_reflection_snapshots_ts
                ON reflection_snapshots(timestamp DESC);

            CREATE TABLE IF NOT EXISTS schema_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_path TEXT NOT NULL,
                captured_at REAL NOT NULL,
                schema_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schema_drifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_path TEXT NOT NULL,
                detected_at REAL NOT NULL,
                drift_type TEXT NOT NULL,
                column_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                acknowledged INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_schema_snapshots_table_ts
                ON schema_snapshots(table_path, captured_at DESC);
            CREATE INDEX IF NOT EXISTS idx_schema_drifts_table_ts
                ON schema_drifts(table_path, detected_at DESC);
        """)


# ── Connection Profiles ──────────────────────────────────────────

def save_connection_profile(profile):
    """Save or update a connection profile."""
    now = time.time()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM connection_profiles WHERE name = ?",
            (profile["name"],)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE connection_profiles SET
                    host=?, port=?, auth_type=?, username=?, password=?,
                    pat_token=?, is_cloud=?, cloud_project_id=?, use_ssl=?,
                    is_default=?, updated_at=?
                WHERE name=?
            """, (
                profile.get("host", "localhost"),
                profile.get("port", 9047),
                profile.get("auth_type", "password"),
                profile.get("username"),
                profile.get("password"),
                profile.get("pat_token"),
                1 if profile.get("is_cloud") else 0,
                profile.get("cloud_project_id"),
                1 if profile.get("use_ssl") else 0,
                1 if profile.get("is_default") else 0,
                now,
                profile["name"]
            ))
        else:
            conn.execute("""
                INSERT INTO connection_profiles
                    (name, host, port, auth_type, username, password, pat_token,
                     is_cloud, cloud_project_id, use_ssl, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile["name"],
                profile.get("host", "localhost"),
                profile.get("port", 9047),
                profile.get("auth_type", "password"),
                profile.get("username"),
                profile.get("password"),
                profile.get("pat_token"),
                1 if profile.get("is_cloud") else 0,
                profile.get("cloud_project_id"),
                1 if profile.get("use_ssl") else 0,
                1 if profile.get("is_default") else 0,
                now, now
            ))

        # If setting as default, unset others
        if profile.get("is_default"):
            conn.execute(
                "UPDATE connection_profiles SET is_default=0 WHERE name != ?",
                (profile["name"],)
            )


def get_connection_profiles():
    """Get all connection profiles."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM connection_profiles ORDER BY is_default DESC, name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_default_profile():
    """Get the default connection profile."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM connection_profiles WHERE is_default=1 LIMIT 1"
        ).fetchone()
        if row:
            return dict(row)
        # Fallback to first profile
        row = conn.execute(
            "SELECT * FROM connection_profiles ORDER BY id LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def delete_connection_profile(name):
    """Delete a connection profile by name."""
    with get_connection() as conn:
        conn.execute("DELETE FROM connection_profiles WHERE name=?", (name,))


# ── Alert Rules ──────────────────────────────────────────────────

def save_alert_rule(rule):
    """Save or update an alert rule."""
    now = time.time()
    with get_connection() as conn:
        if rule.get("id"):
            conn.execute("""
                UPDATE alert_rules SET
                    name=?, rule_type=?, threshold_value=?, threshold_unit=?,
                    window_minutes=?, cooldown_minutes=?, severity=?, enabled=?,
                    notify_email=?, notify_webhook=?, updated_at=?
                WHERE id=?
            """, (
                rule["name"], rule["rule_type"],
                rule["threshold_value"], rule.get("threshold_unit"),
                rule.get("window_minutes", 5),
                rule.get("cooldown_minutes", 15),
                rule.get("severity", "warning"),
                1 if rule.get("enabled", True) else 0,
                1 if rule.get("notify_email") else 0,
                1 if rule.get("notify_webhook") else 0,
                now, rule["id"]
            ))
            return rule["id"]
        else:
            cursor = conn.execute("""
                INSERT INTO alert_rules
                    (name, rule_type, threshold_value, threshold_unit,
                     window_minutes, cooldown_minutes, severity, enabled,
                     notify_email, notify_webhook, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule["name"], rule["rule_type"],
                rule["threshold_value"], rule.get("threshold_unit"),
                rule.get("window_minutes", 5),
                rule.get("cooldown_minutes", 15),
                rule.get("severity", "warning"),
                1 if rule.get("enabled", True) else 0,
                1 if rule.get("notify_email") else 0,
                1 if rule.get("notify_webhook") else 0,
                now, now
            ))
            return cursor.lastrowid


def get_alert_rules():
    """Get all alert rules."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM alert_rules ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_alert_rule(rule_id):
    """Delete an alert rule."""
    with get_connection() as conn:
        conn.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))


def toggle_alert_rule(rule_id, enabled):
    """Enable or disable an alert rule."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE alert_rules SET enabled=?, updated_at=? WHERE id=?",
            (1 if enabled else 0, time.time(), rule_id)
        )


# ── Alert History ────────────────────────────────────────────────

def add_alert_event(rule_id, rule_name, rule_type, severity, message, details=None):
    """Record a triggered alert."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO alert_history
                (rule_id, rule_name, rule_type, severity, message, details, triggered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            rule_id, rule_name, rule_type, severity, message,
            json.dumps(details) if details else None,
            time.time()
        ))
        # Keep only last 1000 alerts
        conn.execute("""
            DELETE FROM alert_history WHERE id NOT IN (
                SELECT id FROM alert_history ORDER BY triggered_at DESC LIMIT 1000
            )
        """)


def get_alert_history(limit=100):
    """Get recent alert history."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM alert_history ORDER BY triggered_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def acknowledge_alert(alert_id):
    """Acknowledge an alert."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE alert_history SET acknowledged=1, acknowledged_at=? WHERE id=?",
            (time.time(), alert_id)
        )


# ── Query Snapshots ──────────────────────────────────────────────

def add_query_snapshot(active, queued, completed, failed, avg_duration_ms=0):
    """Record a point-in-time query metrics snapshot."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO query_snapshots
                (timestamp, active_count, queued_count, completed_count,
                 failed_count, avg_duration_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (time.time(), active, queued, completed, failed, avg_duration_ms))
        # Keep only last 24 hours of snapshots
        cutoff = time.time() - 86400
        conn.execute(
            "DELETE FROM query_snapshots WHERE timestamp < ?", (cutoff,)
        )


def get_query_snapshots(hours=1):
    """Get query snapshots for the last N hours."""
    cutoff = time.time() - (hours * 3600)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM query_snapshots WHERE timestamp > ? ORDER BY timestamp",
            (cutoff,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Engine Snapshots ─────────────────────────────────────────────

def add_engine_snapshot(node_count, overall_pressure, total_heap_used,
                        total_heap_max, health_score, critical_nodes=0,
                        warning_nodes=0):
    """Record engine health snapshot for trend tracking."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO engine_snapshots
                (timestamp, node_count, overall_pressure, total_heap_used,
                 total_heap_max, health_score, critical_nodes, warning_nodes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (time.time(), node_count, overall_pressure, total_heap_used,
              total_heap_max, health_score, critical_nodes, warning_nodes))
        # Keep only last 24 hours
        cutoff = time.time() - 86400
        conn.execute(
            "DELETE FROM engine_snapshots WHERE timestamp < ?", (cutoff,)
        )


def get_engine_snapshots(hours=4):
    """Get engine snapshots for trend charts."""
    cutoff = time.time() - (hours * 3600)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM engine_snapshots WHERE timestamp > ? ORDER BY timestamp",
            (cutoff,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Reflection Snapshots ─────────────────────────────────────────

def add_reflection_snapshot(total, active, failed, dead_accel,
                            health_score, avg_refresh_ms,
                            total_footprint_bytes, wasted_bytes):
    """Record reflection health snapshot for trend tracking."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO reflection_snapshots
                (timestamp, total_reflections, active_count, failed_count,
                 dead_accel_count, health_score, avg_refresh_ms,
                 total_footprint_bytes, wasted_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (time.time(), total, active, failed, dead_accel,
              health_score, avg_refresh_ms, total_footprint_bytes, wasted_bytes))
        cutoff = time.time() - 86400
        conn.execute(
            "DELETE FROM reflection_snapshots WHERE timestamp < ?", (cutoff,)
        )


def get_reflection_snapshots(hours=4):
    """Get reflection snapshots for trend charts."""
    cutoff = time.time() - (hours * 3600)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM reflection_snapshots WHERE timestamp > ? ORDER BY timestamp",
            (cutoff,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Watched Tables (Iceberg) ────────────────────────────────────

def save_watched_table(table_path, label=None):
    """Add an Iceberg table to watch list."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO watched_tables (table_path, label, added_at)
            VALUES (?, ?, ?)
            ON CONFLICT(table_path) DO UPDATE SET
                label=excluded.label
        """, (table_path, label or table_path.split(".")[-1], time.time()))


def get_watched_tables():
    """Get all watched Iceberg tables."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM watched_tables ORDER BY added_at"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_watched_table(table_id):
    """Remove a watched table."""
    with get_connection() as conn:
        conn.execute("DELETE FROM watched_tables WHERE id=?", (table_id,))


def update_watched_table_health(table_id, health_json):
    """Update the last health check result for a watched table."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE watched_tables SET last_checked=?, last_health=? WHERE id=?",
            (time.time(), json.dumps(health_json), table_id)
        )


# ── Notification Config ──────────────────────────────────────────

def save_notification_config(channel, config, enabled=True):
    """Save notification channel configuration."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO notification_config (channel, config, enabled, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(channel) DO UPDATE SET
                config=excluded.config, enabled=excluded.enabled, updated_at=excluded.updated_at
        """, (channel, json.dumps(config), 1 if enabled else 0, time.time()))


def get_notification_config(channel):
    """Get notification channel config."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM notification_config WHERE channel=?", (channel,)
        ).fetchone()
        if row:
            result = dict(row)
            result["config"] = json.loads(result["config"])
            return result
        return None


def get_all_notification_configs():
    """Get all notification configs."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM notification_config").fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["config"] = json.loads(d["config"])
            results.append(d)
        return results


# ── Dashboard Layout ─────────────────────────────────────────────

# Default widget visibility
DEFAULT_LAYOUT = {
    "cluster_health": True,
    "active_queries": True,
    "query_rate": True,
    "acceleration_rate": True,
    "sources_memory": True,
    "slow_queries": True,
    "recent_alerts": True,
    "success_rate": True,
    "reflection_savings": True,
    "queue_wait": True,
    "top_users": True,
    "top_datasets": True,
    "duration_distribution": True,
    "query_lifecycle": True,
    "error_patterns": True,
    "query_types": True,
    "scan_efficiency": True,
    "reflection_efficiency": True,
    # New enhanced monitors
    "engine_health": True,
    "engine_trends": True,
    "reflection_health": True,
    "dead_accelerations": True,
    "iceberg_health": True,
}


def get_dashboard_layout():
    """Get saved dashboard layout or defaults."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT layout FROM dashboard_layout WHERE id=1"
        ).fetchone()
        if row:
            saved = json.loads(row["layout"])
            # Merge with defaults (add new widgets)
            merged = {**DEFAULT_LAYOUT, **saved}
            return merged
        return DEFAULT_LAYOUT.copy()


def save_dashboard_layout(layout):
    """Save dashboard widget visibility preferences."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO dashboard_layout (id, layout, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                layout=excluded.layout, updated_at=excluded.updated_at
        """, (json.dumps(layout), time.time()))


# ── Schema Drift ─────────────────────────────────────────────────

def save_schema_snapshot(table_path, columns):
    """Persist a schema snapshot and return list of detected drifts."""
    now = time.time()
    schema_json = json.dumps(columns)
    drifts = []

    with get_connection() as conn:
        # Get previous snapshot for this table
        prev_row = conn.execute("""
            SELECT schema_json FROM schema_snapshots
            WHERE table_path = ?
            ORDER BY captured_at DESC LIMIT 1
        """, (table_path,)).fetchone()

        if prev_row:
            prev_cols = {c["name"]: c for c in json.loads(prev_row["schema_json"])}
            new_cols = {c["name"]: c for c in columns}

            for name, col in new_cols.items():
                if name not in prev_cols:
                    drifts.append(("column_added", name, None, col.get("type")))
                elif prev_cols[name].get("type") != col.get("type"):
                    drifts.append(("type_changed", name,
                                   prev_cols[name].get("type"), col.get("type")))
                elif prev_cols[name].get("nullable") != col.get("nullable"):
                    drifts.append(("nullability_changed", name,
                                   str(prev_cols[name].get("nullable")),
                                   str(col.get("nullable"))))

            for name in prev_cols:
                if name not in new_cols:
                    drifts.append(("column_dropped", name, prev_cols[name].get("type"), None))

        conn.execute("""
            INSERT INTO schema_snapshots (table_path, captured_at, schema_json)
            VALUES (?, ?, ?)
        """, (table_path, now, schema_json))

        for drift_type, col_name, old_val, new_val in drifts:
            conn.execute("""
                INSERT INTO schema_drifts
                    (table_path, detected_at, drift_type, column_name, old_value, new_value)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (table_path, now, drift_type, col_name, old_val, new_val))

        # Retain only 90 days of snapshots per table
        cutoff = now - 90 * 86400
        conn.execute(
            "DELETE FROM schema_snapshots WHERE table_path=? AND captured_at < ?",
            (table_path, cutoff)
        )

    return drifts


def get_schema_history(table_path, limit=50):
    """Get schema snapshots for a table, newest first."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, table_path, captured_at, schema_json
            FROM schema_snapshots
            WHERE table_path = ?
            ORDER BY captured_at DESC LIMIT ?
        """, (table_path, limit)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["columns"] = json.loads(d.pop("schema_json"))
            results.append(d)
        return results


def get_schema_drifts(table_path=None, limit=200):
    """Get schema drift events, optionally filtered by table."""
    with get_connection() as conn:
        if table_path:
            rows = conn.execute("""
                SELECT * FROM schema_drifts
                WHERE table_path = ?
                ORDER BY detected_at DESC LIMIT ?
            """, (table_path, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM schema_drifts
                ORDER BY detected_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def acknowledge_schema_drift(drift_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE schema_drifts SET acknowledged=1 WHERE id=?", (drift_id,)
        )


def get_latest_schema(table_path):
    """Get the most recent schema snapshot columns for a table."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT schema_json FROM schema_snapshots
            WHERE table_path = ?
            ORDER BY captured_at DESC LIMIT 1
        """, (table_path,)).fetchone()
        if row:
            return json.loads(row["schema_json"])
        return None
