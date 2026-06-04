"""
Alert engine for Dremio Lakehouse Monitor.
Evaluates threshold rules against polled data and triggers notifications.
"""

import time
import logging
from lib import db

logger = logging.getLogger("dremio-monitor")


class AlertEngine:
    def __init__(self, notifier=None):
        self.notifier = notifier
        self._last_triggered = {}

    def evaluate(self, poller_state):
        rules = db.get_alert_rules()
        triggered = []
        for rule in rules:
            if not rule.get("enabled"):
                continue
            rule_id = rule["id"]
            cooldown = rule.get("cooldown_minutes", 15) * 60
            last = self._last_triggered.get(rule_id, 0)
            if time.time() - last < cooldown:
                continue
            alert = self._check_rule(rule["rule_type"], rule["threshold_value"], rule, poller_state)
            if alert:
                alert["rule_id"] = rule_id
                alert["rule_name"] = rule["name"]
                alert["rule_type"] = rule["rule_type"]
                alert["severity"] = rule.get("severity", "warning")
                db.add_alert_event(rule_id, alert["rule_name"], rule["rule_type"],
                                   alert["severity"], alert["message"], alert.get("details"))
                if self.notifier:
                    if rule.get("notify_email"):
                        try: self.notifier.send_email(alert)
                        except Exception as e: logger.error(f"Email failed: {e}")
                    if rule.get("notify_webhook"):
                        try: self.notifier.send_webhook(alert)
                        except Exception as e: logger.error(f"Webhook failed: {e}")
                self._last_triggered[rule_id] = time.time()
                triggered.append(alert)
                logger.warning(f"Alert: [{alert['severity'].upper()}] {alert['message']}")
        return triggered

    def _check_rule(self, rule_type, threshold, rule, state):
        checks = {
            "query_duration": self._check_query_duration,
            "failed_jobs": self._check_failed_jobs,
            "reflection_failure": self._check_reflection_failures,
            "memory_pressure": self._check_memory_pressure,
            "source_down": self._check_source_down,
            "queue_depth": self._check_queue_depth,
            "schema_drift": self._check_schema_drift,
        }
        fn = checks.get(rule_type)
        if fn:
            if rule_type in ("source_down", "schema_drift"):
                return fn(state)
            return fn(threshold, state)
        return None

    def _check_query_duration(self, threshold_min, state):
        active = state.get("active_jobs", [])
        long_running = []
        for job in active:
            started = job.get("attempt_started_ts") or job.get("submitted_ts")
            if not started:
                continue
            try:
                if isinstance(started, str) and "T" in started:
                    from datetime import datetime
                    dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    started_epoch = dt.timestamp()
                else:
                    started_epoch = float(started) / 1000
                dur = (time.time() - started_epoch) / 60
                if dur >= threshold_min:
                    long_running.append({"job_id": job.get("job_id"), "user": job.get("user"),
                                         "duration_minutes": round(dur, 1)})
            except (ValueError, TypeError):
                continue
        if long_running:
            return {"message": f"{len(long_running)} query(ies) running > {threshold_min}min",
                    "details": {"queries": long_running}}
        return None

    def _check_failed_jobs(self, threshold, state):
        failed = int(state.get("job_counts", {}).get("failed", 0))
        if failed >= threshold:
            return {"message": f"{failed} failed jobs (threshold: {int(threshold)})",
                    "details": {"failed_count": failed}}
        return None

    def _check_reflection_failures(self, threshold, state):
        failed = [r for r in state.get("reflections", []) if r.get("status") == "FAILED"]
        if len(failed) >= threshold:
            return {"message": f"{len(failed)} reflection(s) FAILED",
                    "details": {"reflections": [{"name": r.get("reflection_name"),
                                "error": r.get("last_failure_message", "")[:200]} for r in failed[:10]]}}
        return None

    def _check_memory_pressure(self, threshold_pct, state):
        high = []
        for node in state.get("memory", []):
            try:
                cur = int(node.get("heap_current", 0))
                mx = int(node.get("heap_max", 1))
                if mx > 0:
                    pct = (cur / mx) * 100
                    if pct >= threshold_pct:
                        high.append({"hostname": node.get("hostname"), "heap_pct": round(pct, 1)})
            except (ValueError, TypeError):
                continue
        if high:
            return {"message": f"{len(high)} node(s) memory > {threshold_pct}%",
                    "details": {"nodes": high}}
        return None

    def _check_source_down(self, state):
        bad = []
        for src in state.get("sources", []):
            status = src.get("state", {}).get("status", "") or src.get("status", {}).get("health", "")
            if status.lower() not in ("good", "healthy", ""):
                bad.append({"name": src.get("name"), "status": status})
        if bad:
            return {"message": f"{len(bad)} source(s) unhealthy", "details": {"sources": bad}}
        return None

    def _check_queue_depth(self, threshold, state):
        queued = [j for j in state.get("active_jobs", []) if j.get("status") == "ENQUEUED"]
        if len(queued) >= threshold:
            return {"message": f"{len(queued)} queries queued (threshold: {int(threshold)})",
                    "details": {"queued_count": len(queued)}}
        return None

    def _check_schema_drift(self, state):
        drifts = state.get("schema_drift", [])
        if not drifts:
            return None
        drops = [d for d in drifts if d.get("drift_type") == "column_dropped"]
        changes = [d for d in drifts if d.get("drift_type") == "type_changed"]
        additions = [d for d in drifts if d.get("drift_type") == "column_added"]
        parts = []
        if drops:
            parts.append(f"{len(drops)} column(s) dropped")
        if changes:
            parts.append(f"{len(changes)} type change(s)")
        if additions:
            parts.append(f"{len(additions)} column(s) added")
        return {
            "message": f"Schema drift detected: {', '.join(parts)}",
            "details": {"drifts": drifts[:20]},
        }
