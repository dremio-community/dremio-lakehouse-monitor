"""
Background polling engine for Dremio Lakehouse Monitor.
Periodically queries Dremio APIs and pushes updates to connected clients.
"""

import threading
import time
import json
import logging
from lib.dremio_client import DremioClient, DremioClientError
from lib import db

logger = logging.getLogger("dremio-monitor")


class Poller:
    """
    Background poller that periodically queries Dremio and maintains
    current state. Pushes diffs to WebSocket clients via callback.
    """

    def __init__(self, push_callback=None):
        """
        Args:
            push_callback: function(event_type, data) called when state changes.
        """
        self.push_callback = push_callback
        self.client = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # Current state
        self.state = {
            "connected": False,
            "server_status": "UNKNOWN",
            "sources": [],
            "active_jobs": [],
            "recent_jobs": [],
            "reflections": [],
            "materializations": [],
            "memory": [],
            "job_counts": {},
            "top_users": [],
            "top_datasets": [],
            "duration_distribution": {},
            "success_breakdown": {},
            "query_lifecycle": {},
            "error_patterns": [],
            "query_types": [],
            "scan_efficiency": {},
            "reflection_efficiency": [],
            # New enhanced monitors
            "engine_health": {},
            "reflection_health": {},
            "thread_info": [],
            "iceberg_health": [],
            "c3_hit_rates": {},
            "wlm_queue_metrics": [],
            "spill_to_disk": [],
            "catalog_sync_health": [],
            "iceberg_maintenance": [],
            "autoscaling_events": [],
            "schema_drift": [],
            "last_updated": 0,
            "error": None,
        }

        # Poll intervals (seconds)
        self.intervals = {
            "server_status": 5,
            "active_jobs": 5,
            "sources": 30,
            "recent_jobs": 15,
            "reflections": 30,
            "materializations": 60,
            "memory": 10,
            "job_counts": 15,
            "top_users": 60,
            "top_datasets": 60,
            "duration_distribution": 60,
            "success_breakdown": 30,
            "query_lifecycle": 30,
            "error_patterns": 60,
            "query_types": 60,
            "scan_efficiency": 30,
            "reflection_efficiency": 60,
            # New enhanced monitors
            "engine_health": 15,
            "reflection_health": 60,
            "thread_info": 30,
            "iceberg_health": 300,
            "c3_hit_rates": 30,
            "wlm_queue_metrics": 30,
            "spill_to_disk": 30,
            "catalog_sync_health": 120,
            "iceberg_maintenance": 120,
            "autoscaling_events": 60,
            "schema_drift": 300,
        }

        # Last poll timestamps
        self._last_poll = {k: 0 for k in self.intervals}

    def configure(self, profile):
        """Configure with a connection profile."""
        with self._lock:
            try:
                self.client = DremioClient(profile)
                success, msg = self.client.test_connection()
                if success:
                    self.state["connected"] = True
                    self.state["error"] = None
                    logger.info(f"Connected to Dremio: {msg}")
                else:
                    self.state["connected"] = False
                    self.state["error"] = msg
                    logger.warning(f"Connection test failed: {msg}")
                return success, msg
            except Exception as e:
                self.state["connected"] = False
                self.state["error"] = str(e)
                return False, str(e)

    def start(self):
        """Start the background polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Poller started")

    def stop(self):
        """Stop the background polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Poller stopped")

    def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            if not self.state["connected"] or not self.client:
                time.sleep(2)
                continue

            now = time.time()

            try:
                # Poll each data source at its configured interval
                for key, interval in self.intervals.items():
                    if now - self._last_poll[key] >= interval:
                        self._poll_one(key)
                        self._last_poll[key] = now

                self.state["last_updated"] = now
                self.state["error"] = None

            except DremioClientError as e:
                logger.warning(f"Poll error: {e}")
                self.state["error"] = str(e)
                if e.status_code == 401:
                    # Token expired, force re-auth
                    self.client._token = None
                    self.client._token_expires = 0

            except Exception as e:
                import traceback
                logger.error(f"Unexpected poll error: {type(e).__name__}: {e}")
                logger.debug(traceback.format_exc())
                self.state["error"] = str(e)

            time.sleep(1)

    def _poll_one(self, key):
        """Poll a single data source and push updates if changed."""
        old_data = self.state.get(key)

        if key == "server_status":
            new_data = self.client.get_server_status()
        elif key == "active_jobs":
            new_data = self.client.get_active_jobs()
        elif key == "sources":
            new_data = self.client.get_sources()
        elif key == "recent_jobs":
            new_data = self.client.get_recent_jobs()
        elif key == "reflections":
            new_data = self.client.get_reflections()
        elif key == "materializations":
            new_data = self.client.get_materializations()
        elif key == "memory":
            new_data = self.client.get_memory_usage()
        elif key == "job_counts":
            counts = self.client.get_job_counts()
            new_data = counts[0] if counts else {}
        elif key == "top_users":
            new_data = self.client.get_top_users()
        elif key == "top_datasets":
            new_data = self.client.get_top_datasets()
        elif key == "duration_distribution":
            dist = self.client.get_query_duration_distribution()
            new_data = dist[0] if dist else {}
        elif key == "success_breakdown":
            bd = self.client.get_query_success_breakdown()
            new_data = bd[0] if bd else {}
        elif key == "query_lifecycle":
            lc = self.client.get_query_lifecycle_stats()
            new_data = lc[0] if lc else {}
        elif key == "error_patterns":
            new_data = self.client.get_error_patterns()
        elif key == "query_types":
            new_data = self.client.get_query_type_breakdown()
        elif key == "scan_efficiency":
            se = self.client.get_scan_efficiency()
            new_data = se[0] if se else {}
        elif key == "reflection_efficiency":
            new_data = self.client.get_reflection_efficiency()
        elif key == "engine_health":
            new_data = self.client.get_engine_health()
        elif key == "reflection_health":
            new_data = self.client.get_reflection_health_analysis()
        elif key == "thread_info":
            new_data = self.client.get_thread_info()
        elif key == "iceberg_health":
            new_data = self._poll_iceberg_health()
        elif key == "c3_hit_rates":
            new_data = self.client.get_c3_hit_rates()
        elif key == "wlm_queue_metrics":
            new_data = self.client.get_wlm_queue_metrics()
        elif key == "spill_to_disk":
            new_data = self.client.get_spill_to_disk()
        elif key == "catalog_sync_health":
            new_data = self.client.get_catalog_sync_health()
        elif key == "iceberg_maintenance":
            new_data = self.client.get_iceberg_maintenance()
        elif key == "autoscaling_events":
            new_data = self.client.get_autoscaling_events()
        elif key == "schema_drift":
            new_data = self._poll_schema_drift()
        else:
            return

        # Update state
        with self._lock:
            self.state[key] = new_data

        # Record query snapshots for trend charts
        if key == "active_jobs":
            active = len(new_data) if isinstance(new_data, list) else 0
            queued = sum(1 for j in (new_data or [])
                        if j.get("status") == "ENQUEUED")
            try:
                db.add_query_snapshot(
                    active=active,
                    queued=queued,
                    completed=self.state.get("job_counts", {}).get("completed", 0),
                    failed=self.state.get("job_counts", {}).get("failed", 0),
                    avg_duration_ms=self.state.get("job_counts", {}).get("avg_cpu_ms", 0)
                )
            except Exception:
                pass  # Don't fail polling on DB write errors

        # Record snapshots for trend tracking
        if key == "engine_health" and isinstance(new_data, dict):
            try:
                db.add_engine_snapshot(
                    node_count=new_data.get("node_count", 0),
                    overall_pressure=new_data.get("overall_pressure", 0),
                    total_heap_used=new_data.get("total_heap_used", 0),
                    total_heap_max=new_data.get("total_heap_max", 0),
                    health_score=new_data.get("health_score", 0),
                    critical_nodes=new_data.get("critical_nodes", 0),
                    warning_nodes=new_data.get("warning_nodes", 0),
                )
            except Exception:
                pass

        if key == "reflection_health" and isinstance(new_data, dict):
            try:
                db.add_reflection_snapshot(
                    total=new_data.get("total_reflections", 0),
                    active=new_data.get("active_count", 0),
                    failed=new_data.get("failed_count", 0),
                    dead_accel=len(new_data.get("dead_accelerations", [])),
                    health_score=new_data.get("health_score", 0),
                    avg_refresh_ms=new_data.get("avg_refresh_ms", 0),
                    total_footprint_bytes=new_data.get("total_footprint_bytes", 0),
                    wasted_bytes=new_data.get("wasted_footprint_bytes", 0),
                )
            except Exception:
                pass

        # Push to WebSocket clients if data changed
        if self.push_callback and self._data_changed(old_data, new_data):
            try:
                self.push_callback(key, new_data)
            except Exception as e:
                logger.warning(f"Push callback error: {e}")

    def _data_changed(self, old, new):
        """Check if data has changed (simple JSON comparison)."""
        try:
            return json.dumps(old, sort_keys=True, default=str) != \
                   json.dumps(new, sort_keys=True, default=str)
        except Exception:
            return True  # If we can't compare, assume changed

    def get_state(self):
        """Get current snapshot of all polled data."""
        with self._lock:
            return dict(self.state)

    def get_dashboard_summary(self):
        """Get a summary dict for the dashboard overview."""
        with self._lock:
            active_jobs = self.state.get("active_jobs", [])
            sources = self.state.get("sources", [])
            reflections = self.state.get("reflections", [])
            memory = self.state.get("memory", [])
            job_counts = self.state.get("job_counts", {})

            # Calculate health score (0-100)
            health_score = 100
            health_issues = []

            if self.state["server_status"] != "OK":
                health_score -= 50
                health_issues.append("Coordinator not healthy")

            bad_sources = [s for s in sources
                          if s.get("state", {}).get("status") != "good"
                          and s.get("status", {}).get("health") != "HEALTHY"]
            if bad_sources:
                health_score -= 10 * len(bad_sources)
                health_issues.append(f"{len(bad_sources)} source(s) unhealthy")

            failed_reflections = [r for r in reflections
                                  if r.get("status") == "FAILED"]
            if failed_reflections:
                health_score -= 5 * len(failed_reflections)
                health_issues.append(f"{len(failed_reflections)} reflection(s) failed")

            # Memory pressure
            for node in memory:
                try:
                    heap_current = int(node.get("heap_current", 0))
                    heap_max = int(node.get("heap_max", 1))
                    if heap_max > 0:
                        pct = (heap_current / heap_max) * 100
                        if pct > 90:
                            health_score -= 15
                            health_issues.append(
                                f"Memory critical on {node.get('hostname', 'unknown')}")
                        elif pct > 75:
                            health_score -= 5
                except (ValueError, TypeError):
                    pass

            health_score = max(0, min(100, health_score))

            return {
                "connected": self.state["connected"],
                "server_status": self.state["server_status"],
                "health_score": health_score,
                "health_issues": health_issues,
                "active_query_count": len(active_jobs),
                "queued_count": sum(1 for j in active_jobs
                                    if j.get("status") == "ENQUEUED"),
                "source_count": len(sources),
                "sources_healthy": len(sources) - len(bad_sources),
                "sources_unhealthy": len(bad_sources),
                "reflection_count": len(reflections),
                "reflections_active": sum(1 for r in reflections
                                          if r.get("status") == "ACTIVE"),
                "reflections_failed": len(failed_reflections),
                "job_counts": job_counts,
                "memory_nodes": [{
                    "hostname": n.get("hostname", "unknown"),
                    "heap_current": n.get("heap_current", 0),
                    "heap_max": n.get("heap_max", 0),
                    "direct_current": n.get("direct_current", 0),
                    "direct_max": n.get("direct_max", 0),
                } for n in memory],
                "top_users": self.state.get("top_users", []),
                "top_datasets": self.state.get("top_datasets", []),
                "duration_distribution": self.state.get("duration_distribution", {}),
                "success_breakdown": self.state.get("success_breakdown", {}),
                "query_lifecycle": self.state.get("query_lifecycle", {}),
                "error_patterns": self.state.get("error_patterns", []),
                "query_types": self.state.get("query_types", []),
                "scan_efficiency": self.state.get("scan_efficiency", {}),
                "reflection_efficiency": self.state.get("reflection_efficiency", []),
                # New enhanced monitors
                "engine_health": self.state.get("engine_health", {}),
                "reflection_health": self.state.get("reflection_health", {}),
                "thread_info": self.state.get("thread_info", []),
                "iceberg_health": self.state.get("iceberg_health", []),
                "c3_hit_rates": self.state.get("c3_hit_rates", {}),
                "wlm_queue_metrics": self.state.get("wlm_queue_metrics", []),
                "spill_to_disk": self.state.get("spill_to_disk", []),
                "catalog_sync_health": self.state.get("catalog_sync_health", []),
                "iceberg_maintenance": self.state.get("iceberg_maintenance", []),
                "autoscaling_events": self.state.get("autoscaling_events", []),
                "schema_drift": self.state.get("schema_drift", []),
                "last_updated": self.state["last_updated"],
                "error": self.state["error"],
            }

    def _poll_schema_drift(self):
        """Snapshot schemas of all watched tables and return recent drift events."""
        tables = db.get_watched_tables()
        if not tables:
            return []

        all_drifts = []
        for t in tables:
            try:
                cols = self.client.describe_table(t["table_path"])
                if not cols:
                    continue
                drifts = db.save_schema_snapshot(t["table_path"], cols)
                for dtype, col_name, old_val, new_val in drifts:
                    all_drifts.append({
                        "table": t["table_path"],
                        "label": t.get("label", t["table_path"]),
                        "drift_type": dtype,
                        "column_name": col_name,
                        "old_value": old_val,
                        "new_value": new_val,
                    })
                    logger.warning(
                        f"Schema drift on {t['table_path']}: "
                        f"{dtype} — column '{col_name}'"
                    )
            except Exception as e:
                logger.warning(f"Schema drift poll error for {t['table_path']}: {e}")

        return all_drifts

    def _poll_iceberg_health(self):
        """Poll health for all watched Iceberg tables."""
        tables = db.get_watched_tables()
        if not tables:
            return []

        results = []
        for t in tables:
            try:
                health = self.client.get_iceberg_table_health(t["table_path"])
                health["id"] = t["id"]
                health["label"] = t.get("label", t["table_path"])
                results.append(health)
                # Update stored health
                db.update_watched_table_health(t["id"], health)
            except Exception as e:
                results.append({
                    "id": t["id"],
                    "table": t["table_path"],
                    "label": t.get("label", t["table_path"]),
                    "error": str(e),
                })
        return results
