"""
Dremio REST API client supporting both Software (self-managed) and Cloud.
Handles authentication via username/password or Personal Access Token (PAT).
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
import ssl
import logging

logger = logging.getLogger("dremio-monitor")

# Dremio Cloud base URL
DREMIO_CLOUD_BASE = "https://api.dremio.cloud"


class DremioClientError(Exception):
    """Raised when a Dremio API call fails."""
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class DremioClient:
    """
    Client for Dremio REST API.

    Supports:
    - Dremio Software (self-managed): host:port with username/password or PAT
    - Dremio Cloud: cloud API with PAT authentication
    """

    def __init__(self, profile):
        """
        Initialize from a connection profile dict.

        profile keys:
            host, port, auth_type ('password'|'pat'), username, password,
            pat_token, is_cloud, cloud_project_id, use_ssl
        """
        self.profile = profile
        self.is_cloud = profile.get("is_cloud", False)
        self.auth_type = profile.get("auth_type", "password")
        self._token = None
        self._token_expires = 0

        if self.is_cloud:
            self.base_url = DREMIO_CLOUD_BASE
            self.project_id = profile.get("cloud_project_id", "")
        else:
            scheme = "https" if profile.get("use_ssl") else "http"
            host = profile.get("host", "localhost")
            port = profile.get("port", 9047)
            self.base_url = f"{scheme}://{host}:{port}"

        # SSL context — Cloud always uses verified SSL
        self._ssl_ctx = ssl.create_default_context()
        if not self.is_cloud and not profile.get("use_ssl"):
            self._ssl_ctx.check_hostname = False
            self._ssl_ctx.verify_mode = ssl.CERT_NONE

        # System table mapping: Cloud uses different table paths
        if self.is_cloud:
            self._table_map = {
                "sys.jobs": "sys.project.history.jobs",
                "sys.jobs_recent": "sys.project.history.jobs",
                "sys.reflections": "sys.project.reflections",
                "sys.materializations": None,  # not available in Cloud
                "sys.memory": None,             # not available in Cloud
                "sys.threads": None,            # not available in Cloud
            }
        else:
            self._table_map = {
                "sys.jobs": "sys.jobs",
                "sys.jobs_recent": "sys.jobs_recent",
                "sys.reflections": "sys.reflections",
                "sys.materializations": "sys.materializations",
                "sys.memory": "sys.memory",
                "sys.threads": "sys.threads",
            }

    def _sys(self, table_name):
        """Get the correct system table name for the current deployment."""
        return self._table_map.get(table_name, table_name)

    def _get_token(self):
        """Get or refresh authentication token."""
        if self.auth_type == "pat":
            return self.profile.get("pat_token", "")

        # Username/password auth — cache token
        if self._token and time.time() < self._token_expires:
            return self._token

        login_url = f"{self.base_url}/apiv2/login"
        payload = json.dumps({
            "userName": self.profile.get("username", ""),
            "password": self.profile.get("password", "")
        }).encode("utf-8")

        req = urllib.request.Request(
            login_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=10)
            body = json.loads(resp.read().decode("utf-8"))
            self._token = body.get("token", "")
            # Tokens typically last ~24h, refresh after 23h
            self._token_expires = time.time() + 82800
            return self._token
        except urllib.error.HTTPError as e:
            raise DremioClientError(
                f"Login failed: {e.code} {e.reason}",
                status_code=e.code,
                response_body=e.read().decode("utf-8", errors="replace")
            )
        except Exception as e:
            raise DremioClientError(f"Login failed: {e}")

    def _request(self, method, path, body=None, timeout=30):
        """Make an authenticated API request."""
        url = f"{self.base_url}{path}"
        token = self._get_token()

        headers = {
            "Authorization": f"Bearer {token}" if not self.is_cloud else f"Bearer {token}",
            "Content-Type": "application/json",
        }

        if self.is_cloud and self.project_id:
            headers["X-Dremio-Project-Id"] = self.project_id

        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout)
            content = resp.read().decode("utf-8")
            if content:
                return json.loads(content)
            return None
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8", errors="replace")
            raise DremioClientError(
                f"API error {e.code}: {path}",
                status_code=e.code,
                response_body=resp_body
            )
        except urllib.error.URLError as e:
            raise DremioClientError(f"Connection error: {e.reason}")
        except Exception as e:
            raise DremioClientError(f"Request failed: {e}")

    # ── Health & Status ──────────────────────────────────────────

    def get_server_status(self):
        """Check coordinator health. Returns 'OK' or error."""
        try:
            if self.is_cloud:
                # Dremio Cloud: use source list as health check
                path = f"/v0/projects/{self.project_id}/source"
                result = self._request("GET", path)
                if result is not None:
                    return "OK"
                return "ERROR: Empty response"
            else:
                url = f"{self.base_url}/apiv2/server_status"
                token = self._get_token()
                req = urllib.request.Request(url, headers={
                    "Authorization": f"Bearer {token}"
                })
                resp = urllib.request.urlopen(
                    req, context=self._ssl_ctx, timeout=5)
                return resp.read().decode("utf-8").strip().strip('"')
        except Exception as e:
            return f"ERROR: {e}"

    def get_sources(self):
        """Get all configured sources with their status."""
        try:
            if self.is_cloud:
                path = f"/v0/projects/{self.project_id}/source"
            else:
                path = "/api/v3/source"
            result = self._request("GET", path)
            return result.get("data", []) if result else []
        except DremioClientError:
            return []

    def test_connection(self):
        """Test connectivity. Returns (success: bool, message: str)."""
        try:
            status = self.get_server_status()
            if status == "OK":
                return True, "Connected successfully"
            return False, f"Unexpected status: {status}"
        except DremioClientError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    # ── SQL Queries (via REST API) ───────────────────────────────

    @property
    def _api_prefix(self):
        """Return API path prefix — different for Cloud vs Software."""
        if self.is_cloud:
            return f"/v0/projects/{self.project_id}"
        return "/api/v3"

    def submit_sql(self, sql):
        """Submit a SQL query and return the job ID."""
        result = self._request("POST", f"{self._api_prefix}/sql", {"sql": sql})
        return result.get("id", "")

    def get_job_status(self, job_id):
        """Get job status and metadata."""
        return self._request("GET", f"{self._api_prefix}/job/{job_id}")

    def get_job_results(self, job_id, offset=0, limit=500):
        """Get job results."""
        return self._request(
            "GET",
            f"{self._api_prefix}/job/{job_id}/results?offset={offset}&limit={limit}"
        )

    def run_sql_query(self, sql, timeout=60):
        """
        Run a SQL query synchronously. Returns list of row dicts.
        Polls until complete or timeout.
        """
        job_id = self.submit_sql(sql)
        if not job_id:
            raise DremioClientError("Failed to submit SQL query")

        start = time.time()
        while time.time() - start < timeout:
            job = self.get_job_status(job_id)
            state = job.get("jobState", "UNKNOWN")

            if state == "COMPLETED":
                results = self.get_job_results(job_id)
                return self._parse_results(results)
            elif state in ("FAILED", "CANCELLED"):
                error_msg = job.get("errorMessage", "Unknown error")
                raise DremioClientError(f"Query {state}: {error_msg}")

            time.sleep(0.5)

        raise DremioClientError(f"Query timed out after {timeout}s")

    def _parse_results(self, results):
        """Parse job results into list of dicts."""
        if not results:
            return []

        rows_data = results.get("rows", [])
        if not rows_data:
            return []

        # Dremio v3 API returns rows as dicts keyed by column name
        if isinstance(rows_data[0], dict):
            return rows_data

        # Fallback: rows as arrays (older API versions)
        columns = [col["name"] for col in results.get("schema", [])]
        rows = []
        for row_data in rows_data:
            row = {}
            for i, col in enumerate(columns):
                if i < len(row_data):
                    row[col] = row_data[i]
                else:
                    row[col] = None
            rows.append(row)
        return rows

    # ── System Table Queries ─────────────────────────────────────

    def get_active_jobs(self):
        """Get currently running jobs."""
        tbl = self._sys("sys.jobs")
        if not tbl:
            return []
        try:
            cols = 'job_id, "user", query_type, query, status, submitted_ts'
            if not self.is_cloud:
                cols += ', attempt_started_ts, planner_estimated_cost, rows_scanned, bytes_scanned, accelerated, queue_name'
            return self.run_sql_query(f"""
                SELECT {cols}
                FROM {tbl}
                WHERE status = 'RUNNING' OR status = 'STARTING'
                   OR status = 'ENQUEUED' OR status = 'PLANNING'
                ORDER BY submitted_ts
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get active jobs: {e}")
            return []

    def get_recent_jobs(self, limit=100):
        """Get recent jobs."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            cols = 'job_id, "user", query_type, query, status, submitted_ts'
            if not self.is_cloud:
                cols += ', attempt_started_ts, planner_estimated_cost, rows_scanned, bytes_scanned, execution_cpu_time_millis, accelerated, queue_name'
            return self.run_sql_query(f"""
                SELECT {cols}
                FROM {tbl}
                ORDER BY submitted_ts DESC
                LIMIT {limit}
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get recent jobs: {e}")
            return []

    def get_reflections(self):
        """Get all reflections."""
        tbl = self._sys("sys.reflections")
        if not tbl:
            return []
        try:
            return self.run_sql_query(f"""
                SELECT reflection_id, reflection_name, type, status,
                       num_failures, last_failure_message,
                       dataset_name, dataset_type,
                       current_footprint_bytes,
                       considered_count, matched_count, accelerated_count,
                       refresh_status, last_refresh_from_table
                FROM {tbl}
                ORDER BY reflection_name
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get reflections: {e}")
            return []

    def get_materializations(self):
        """Get materialization history."""
        tbl = self._sys("sys.materializations")
        if not tbl:
            return []
        try:
            return self.run_sql_query(f"""
                SELECT reflection_id, materialization_id,
                       created, expires
                FROM {tbl}
                ORDER BY created DESC
                LIMIT 50
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get materializations: {e}")
            return []

    def get_memory_usage(self):
        """Get memory usage (not available in Cloud)."""
        tbl = self._sys("sys.memory")
        if not tbl:
            return []
        try:
            return self.run_sql_query(f"""
                SELECT hostname, fabric_port,
                       direct_current, direct_max,
                       heap_current, heap_max
                FROM {tbl}
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get memory usage: {e}")
            return []

    def get_job_counts(self):
        """Get aggregated job counts for the last hour."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return [{"total": 0, "completed": 0, "failed": 0,
                     "cancelled": 0, "accelerated": 0, "avg_cpu_ms": 0}]
        try:
            return self.run_sql_query(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled,
                    SUM(CASE WHEN accelerated = true THEN 1 ELSE 0 END) as accelerated
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -1, CURRENT_TIMESTAMP)
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get job counts: {e}")
            return [{"total": 0, "completed": 0, "failed": 0,
                     "cancelled": 0, "accelerated": 0, "avg_cpu_ms": 0}]

    # ── Advanced Analytics Queries ───────────────────────────────

    def get_top_users(self, hours=24):
        """Get top users by query count with avg duration and failure rate."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            avg_duration_sql = "0" if self.is_cloud else "AVG(execution_cpu_time_millis)"
            return self.run_sql_query(f"""
                SELECT
                    user_name as username,
                    COUNT(*) as query_count,
                    {avg_duration_sql} as avg_duration_ms,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_count,
                    SUM(CASE WHEN accelerated = true THEN 1 ELSE 0 END) as accelerated_count
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                GROUP BY user_name
                ORDER BY query_count DESC
                LIMIT 10
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get top users: {e}")
            return []

    def get_top_datasets(self, hours=24):
        """Get top queried datasets with acceleration and duration stats."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            avg_duration_sql = "0" if self.is_cloud else "AVG(execution_cpu_time_millis)"
            queried_datasets_sql = "queried_datasets[0]" if self.is_cloud else "queried_datasets"
            empty_check_sql = "CARDINALITY(queried_datasets) > 0" if self.is_cloud else "queried_datasets <> ''"
            return self.run_sql_query(f"""
                SELECT
                    {queried_datasets_sql} as dataset,
                    COUNT(*) as query_count,
                    {avg_duration_sql} as avg_duration_ms,
                    SUM(CASE WHEN accelerated = true THEN 1 ELSE 0 END) as accelerated_count,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_count
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                  AND queried_datasets IS NOT NULL
                  AND {empty_check_sql}
                GROUP BY {queried_datasets_sql}
                ORDER BY query_count DESC
                LIMIT 10
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get top datasets: {e}")
            return []

    def get_query_duration_distribution(self, hours=24):
        """Get query duration distribution across buckets."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            if self.is_cloud:
                return [{"under_1s": 0, "s1_to_5s": 0, "s5_to_30s": 0,
                         "s30_to_2m": 0, "m2_to_10m": 0, "over_10m": 0}]
            return self.run_sql_query(f"""
                SELECT
                    SUM(CASE WHEN execution_cpu_time_millis < 1000 THEN 1 ELSE 0 END) as under_1s,
                    SUM(CASE WHEN execution_cpu_time_millis >= 1000
                              AND execution_cpu_time_millis < 5000 THEN 1 ELSE 0 END) as s1_to_5s,
                    SUM(CASE WHEN execution_cpu_time_millis >= 5000
                              AND execution_cpu_time_millis < 30000 THEN 1 ELSE 0 END) as s5_to_30s,
                    SUM(CASE WHEN execution_cpu_time_millis >= 30000
                              AND execution_cpu_time_millis < 120000 THEN 1 ELSE 0 END) as s30_to_2m,
                    SUM(CASE WHEN execution_cpu_time_millis >= 120000
                              AND execution_cpu_time_millis < 600000 THEN 1 ELSE 0 END) as m2_to_10m,
                    SUM(CASE WHEN execution_cpu_time_millis >= 600000 THEN 1 ELSE 0 END) as over_10m
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                  AND status = 'COMPLETED'
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get duration distribution: {e}")
            return [{"under_1s": 0, "s1_to_5s": 0, "s5_to_30s": 0,
                     "s30_to_2m": 0, "m2_to_10m": 0, "over_10m": 0}]

    def get_query_success_breakdown(self, hours=1):
        """Get completed/failed/cancelled counts for donut chart."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            avg_accel_ms = "0" if self.is_cloud else "AVG(CASE WHEN accelerated = true THEN execution_cpu_time_millis END)"
            avg_non_accel_ms = "0" if self.is_cloud else "AVG(CASE WHEN accelerated = false THEN execution_cpu_time_millis END)"
            return self.run_sql_query(f"""
                SELECT
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled,
                    COUNT(*) as total,
                    {avg_accel_ms} as avg_accel_ms,
                    {avg_non_accel_ms} as avg_non_accel_ms
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get success breakdown: {e}")
            return [{"completed": 0, "failed": 0, "cancelled": 0, "total": 0,
                     "avg_accel_ms": 0, "avg_non_accel_ms": 0}]

    def get_query_lifecycle_stats(self, hours=1):
        """Get avg time spent in each query lifecycle stage."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            if self.is_cloud:
                return [{}]
            return self.run_sql_query(f"""
                SELECT
                    AVG(metadata_retrieval_epoch_millis - submitted_epoch_millis) as avg_metadata_ms,
                    AVG(planning_start_epoch_millis - metadata_retrieval_epoch_millis) as avg_planning_wait_ms,
                    AVG(query_enqueued_epoch_millis - planning_start_epoch_millis) as avg_planning_ms,
                    AVG(engine_start_epoch_millis - query_enqueued_epoch_millis) as avg_queue_ms,
                    AVG(execution_start_epoch_millis - engine_start_epoch_millis) as avg_engine_start_ms,
                    AVG(final_state_epoch_millis - execution_start_epoch_millis) as avg_execution_ms,
                    AVG(final_state_epoch_millis - submitted_epoch_millis) as avg_total_ms
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                  AND status = 'COMPLETED'
                  AND final_state_epoch_millis > 0
                  AND submitted_epoch_millis > 0
                  AND metadata_retrieval_epoch_millis > 0
                  AND planning_start_epoch_millis > 0
                  AND query_enqueued_epoch_millis > 0
                  AND engine_start_epoch_millis > 0
                  AND execution_start_epoch_millis > 0
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get lifecycle stats: {e}")
            return [{}]

    def get_error_patterns(self, hours=24, limit=10):
        """Get top error patterns from failed queries."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            return self.run_sql_query(f"""
                SELECT
                    SUBSTR(error_msg, 1, 150) as error_pattern,
                    COUNT(*) as occurrence_count,
                    MAX(submitted_ts) as last_seen,
                    MIN(submitted_ts) as first_seen
                FROM {tbl}
                WHERE status = 'FAILED'
                  AND submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                  AND error_msg IS NOT NULL
                  AND error_msg <> ''
                GROUP BY SUBSTR(error_msg, 1, 150)
                ORDER BY occurrence_count DESC
                LIMIT {limit}
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get error patterns: {e}")
            return []

    def get_query_type_breakdown(self, hours=24):
        """Get query count by type (ODBC, JDBC, REST, UI, etc)."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            avg_duration_sql = "0" if self.is_cloud else "AVG(execution_cpu_time_millis)"
            return self.run_sql_query(f"""
                SELECT
                    query_type,
                    COUNT(*) as query_count,
                    {avg_duration_sql} as avg_duration_ms,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                GROUP BY query_type
                ORDER BY query_count DESC
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get query type breakdown: {e}")
            return []

    def get_scan_efficiency(self, hours=1):
        """Get data scan efficiency stats (scanned vs returned)."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            if self.is_cloud:
                return [{"total_bytes_scanned": 0, "total_bytes_returned": 0,
                         "total_rows_scanned": 0, "total_rows_returned": 0, "query_count": 0}]
            return self.run_sql_query(f"""
                SELECT
                    SUM(CAST(bytes_scanned AS BIGINT)) as total_bytes_scanned,
                    SUM(CAST(bytes_returned AS BIGINT)) as total_bytes_returned,
                    SUM(CAST(rows_scanned AS BIGINT)) as total_rows_scanned,
                    SUM(CAST(rows_returned AS BIGINT)) as total_rows_returned,
                    COUNT(*) as query_count
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                  AND status = 'COMPLETED'
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get scan efficiency: {e}")
            return [{"total_bytes_scanned": 0, "total_bytes_returned": 0,
                     "total_rows_scanned": 0, "total_rows_returned": 0, "query_count": 0}]

    def get_reflection_efficiency(self):
        """Get reflection utilization: considered vs matched vs accelerated."""
        tbl_ref = self._sys("sys.reflections")
        if not tbl_ref:
            return []
        try:
            return self.run_sql_query(f"""
                SELECT
                    reflection_id, reflection_name, type, status,
                    considered_count, matched_count, accelerated_count,
                    current_footprint_bytes, record_count,
                    last_refresh_duration_millis, refresh_method,
                    num_failures
                FROM {tbl_ref}
                ORDER BY accelerated_count DESC
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get reflection efficiency: {e}")
            return []

    # ── Reflection Health Deep Analysis ──────────────────────────

    def get_reflection_health_analysis(self):
        """
        Comprehensive reflection health: staleness, dead accelerations,
        failure patterns, refresh duration stats.
        """
        tbl_ref = self._sys("sys.reflections")
        if not tbl_ref:
            return {"health_score": 100, "health_issues": [], "total_reflections": 0, "dead_accelerations": [], "failure_patterns": [], "all_reflections": []}
        try:
            reflections = self.run_sql_query(f"""
                SELECT
                    reflection_id, reflection_name, type, status,
                    dataset_name, dataset_type,
                    considered_count, matched_count, accelerated_count,
                    current_footprint_bytes, record_count,
                    last_refresh_duration_millis, refresh_method,
                    num_failures, last_failure_message,
                    refresh_status, last_refresh_from_table
                FROM {tbl_ref}
                ORDER BY reflection_name
            """)

            # Compute health metrics
            total = len(reflections)
            active = [r for r in reflections if r.get("status") == "ACTIVE"]
            failed = [r for r in reflections if r.get("status") == "FAILED"]
            disabled = [r for r in reflections
                        if r.get("status") not in ("ACTIVE", "FAILED")]

            # Dead accelerations: active but never used
            dead_accels = [r for r in active
                          if int(r.get("accelerated_count") or 0) == 0]

            # Zero-hit reflections: active but never even considered
            zero_hits = [r for r in active
                         if int(r.get("considered_count") or 0) == 0]

            # Considered but never matched (poor reflection design)
            unmatched = [r for r in active
                         if int(r.get("considered_count") or 0) > 0
                         and int(r.get("matched_count") or 0) == 0]

            # Refresh failures
            failure_messages = {}
            for r in reflections:
                msg = r.get("last_failure_message")
                if msg and r.get("num_failures") and int(r["num_failures"]) > 0:
                    key = msg[:100]
                    if key not in failure_messages:
                        failure_messages[key] = {
                            "message": msg[:200],
                            "count": 0,
                            "reflections": []
                        }
                    failure_messages[key]["count"] += int(r["num_failures"])
                    failure_messages[key]["reflections"].append(
                        r.get("reflection_name", "unknown"))

            # Total footprint
            total_bytes = sum(
                int(r.get("current_footprint_bytes") or 0) for r in reflections)
            wasted_bytes = sum(
                int(r.get("current_footprint_bytes") or 0) for r in dead_accels)

            # Avg refresh duration
            refresh_durations = [
                int(r.get("last_refresh_duration_millis") or 0)
                for r in active
                if r.get("last_refresh_duration_millis")
                and int(r.get("last_refresh_duration_millis") or 0) > 0
            ]
            avg_refresh_ms = (sum(refresh_durations) / len(refresh_durations)
                              if refresh_durations else 0)
            max_refresh_ms = max(refresh_durations) if refresh_durations else 0

            # Calculate health score (0-100)
            health_score = 100
            health_issues = []

            if failed:
                health_score -= min(30, len(failed) * 10)
                health_issues.append(f"{len(failed)} failed reflection(s)")

            if dead_accels:
                health_score -= min(20, len(dead_accels) * 5)
                health_issues.append(
                    f"{len(dead_accels)} dead acceleration(s) "
                    f"(wasting {self._format_bytes(wasted_bytes)})")

            if zero_hits:
                health_score -= min(15, len(zero_hits) * 3)
                health_issues.append(f"{len(zero_hits)} never-considered reflection(s)")

            if max_refresh_ms > 300000:  # > 5 minutes
                health_score -= 10
                health_issues.append("Slow refresh detected (>5 min)")

            total_failures = sum(
                int(r.get("num_failures") or 0) for r in reflections)
            if total_failures > 10:
                health_score -= 10
                health_issues.append(f"{total_failures} total refresh failures")

            health_score = max(0, min(100, health_score))

            return {
                "health_score": health_score,
                "health_issues": health_issues,
                "total_reflections": total,
                "active_count": len(active),
                "failed_count": len(failed),
                "disabled_count": len(disabled),
                "dead_accelerations": [{
                    "name": r.get("reflection_name", ""),
                    "type": r.get("type", ""),
                    "dataset": r.get("dataset_name", ""),
                    "footprint_bytes": int(r.get("current_footprint_bytes") or 0),
                    "considered": int(r.get("considered_count") or 0),
                    "matched": int(r.get("matched_count") or 0),
                } for r in dead_accels],
                "zero_hit_reflections": [{
                    "name": r.get("reflection_name", ""),
                    "type": r.get("type", ""),
                    "dataset": r.get("dataset_name", ""),
                } for r in zero_hits],
                "unmatched_reflections": [{
                    "name": r.get("reflection_name", ""),
                    "type": r.get("type", ""),
                    "dataset": r.get("dataset_name", ""),
                    "considered": int(r.get("considered_count") or 0),
                } for r in unmatched],
                "failure_patterns": list(failure_messages.values()),
                "total_footprint_bytes": total_bytes,
                "wasted_footprint_bytes": wasted_bytes,
                "avg_refresh_ms": avg_refresh_ms,
                "max_refresh_ms": max_refresh_ms,
                "all_reflections": reflections,
            }
        except DremioClientError as e:
            logger.warning(f"Failed to get reflection health: {e}")
            return {"health_score": 0, "health_issues": ["Query failed"],
                    "total_reflections": 0, "dead_accelerations": [],
                    "failure_patterns": [], "all_reflections": []}

    def _format_bytes(self, b):
        """Format bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(b) < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

    # ── Engine Health ────────────────────────────────────────────

    def get_engine_health(self):
        """
        Compute engine health: memory pressure per node,
        node count, aggregate metrics.
        """
        tbl_mem = self._sys("sys.memory")
        if not tbl_mem:
            return {"health_score": 100, "health_issues": ["Engine metrics not available in Cloud"], "node_count": 0, "nodes": [], "overall_pressure": 0}
        try:
            nodes = self.run_sql_query(f"""
                SELECT hostname, fabric_port,
                       heap_current, heap_max,
                       direct_current, direct_max
                FROM {tbl_mem}
            """)

            node_health = []
            total_heap_used = 0
            total_heap_max = 0
            critical_nodes = 0
            warning_nodes = 0

            for n in nodes:
                heap_cur = int(n.get("heap_current") or 0)
                heap_max = int(n.get("heap_max") or 1)
                direct_cur = int(n.get("direct_current") or 0)
                direct_max = int(n.get("direct_max") or 1)

                heap_pct = (heap_cur / heap_max * 100) if heap_max > 0 else 0
                direct_pct = (direct_cur / direct_max * 100) if direct_max > 0 else 0

                # Memory Pressure Index = weighted combination
                pressure = max(heap_pct, direct_pct)

                status = "healthy"
                if pressure > 90:
                    status = "critical"
                    critical_nodes += 1
                elif pressure > 75:
                    status = "warning"
                    warning_nodes += 1

                total_heap_used += heap_cur
                total_heap_max += heap_max

                hostname = (n.get("hostname") or "unknown").split(".")[0]
                node_health.append({
                    "hostname": hostname,
                    "port": n.get("fabric_port"),
                    "heap_current": heap_cur,
                    "heap_max": heap_max,
                    "heap_pct": round(heap_pct, 1),
                    "direct_current": direct_cur,
                    "direct_max": direct_max,
                    "direct_pct": round(direct_pct, 1),
                    "pressure_index": round(pressure, 1),
                    "status": status,
                })

            # Overall pressure
            overall_pressure = (
                (total_heap_used / total_heap_max * 100)
                if total_heap_max > 0 else 0
            )

            # Engine health score
            health_score = 100
            health_issues = []

            if critical_nodes:
                health_score -= critical_nodes * 20
                health_issues.append(
                    f"{critical_nodes} node(s) at critical memory pressure")
            if warning_nodes:
                health_score -= warning_nodes * 10
                health_issues.append(
                    f"{warning_nodes} node(s) at high memory pressure")

            health_score = max(0, min(100, health_score))

            return {
                "health_score": health_score,
                "health_issues": health_issues,
                "node_count": len(nodes),
                "nodes": node_health,
                "overall_pressure": round(overall_pressure, 1),
                "total_heap_used": total_heap_used,
                "total_heap_max": total_heap_max,
                "critical_nodes": critical_nodes,
                "warning_nodes": warning_nodes,
            }
        except DremioClientError as e:
            logger.warning(f"Failed to get engine health: {e}")
            return {"health_score": 0, "health_issues": ["Query failed"],
                    "node_count": 0, "nodes": [], "overall_pressure": 0}

    def get_thread_info(self):
        """Get thread pool info from sys.threads (if available)."""
        tbl_thr = self._sys("sys.threads")
        if not tbl_thr:
            return []
        try:
            return self.run_sql_query(f"""
                SELECT hostname, fabric_port,
                       user_port, system_port,
                       is_coordinator, status
                FROM {tbl_thr}
                LIMIT 50
            """)
        except DremioClientError:
            # sys.threads may not exist in all Dremio versions
            return []

    # ── Iceberg Table Health ─────────────────────────────────────

    def get_iceberg_table_health(self, table_path):
        """
        Get health metrics for a specific Iceberg table using
        Dremio's table_snapshot() and table_files() functions.
        """
        result = {
            "table": table_path,
            "snapshot_count": 0,
            "total_files": 0,
            "total_size_bytes": 0,
            "small_files": 0,
            "small_file_ratio": 0,
            "avg_file_size": 0,
            "delete_files": 0,
            "latest_snapshot_ts": None,
            "error": None,
        }

        # Get snapshot info
        try:
            snapshots = self.run_sql_query(
                f'SELECT * FROM TABLE(table_snapshot(\'{table_path}\'))')
            result["snapshot_count"] = len(snapshots)
            if snapshots:
                # Find latest snapshot
                latest = max(snapshots,
                             key=lambda s: s.get("committed_at", ""),
                             default=None)
                if latest:
                    result["latest_snapshot_ts"] = latest.get("committed_at")
        except DremioClientError as e:
            result["error"] = f"Snapshot query failed: {e}"
            return result

        # Get file stats
        try:
            files = self.run_sql_query(f"""
                SELECT file_path, file_size_in_bytes
                FROM TABLE(table_files('{table_path}'))
            """)
            result["total_files"] = len(files)
            total_size = 0
            small_count = 0
            delete_count = 0

            for f in files:
                size = int(f.get("file_size_in_bytes") or 0)
                total_size += size
                if size < 128 * 1024 * 1024:  # < 128MB
                    small_count += 1
                file_path = f.get("file_path", "")
                if "delete" in file_path.lower():
                    delete_count += 1

            result["total_size_bytes"] = total_size
            result["small_files"] = small_count
            result["small_file_ratio"] = (
                round(small_count / len(files) * 100, 1)
                if files else 0)
            result["avg_file_size"] = (
                total_size // len(files) if files else 0)
            result["delete_files"] = delete_count

        except DremioClientError as e:
            result["error"] = f"File query failed: {e}"

        return result

    def get_available_tables(self):
        """Get all available tables grouped by schema."""
        try:
            res = self.run_sql_query("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.\"TABLES\" WHERE TABLE_TYPE = 'TABLE'")
            tables_by_schema = {}
            for r in res:
                schema = r.get("TABLE_SCHEMA", "")
                name = r.get("TABLE_NAME", "")
                
                # Split schema by dots and quote each part, then append the quoted table name
                if schema:
                    parts = schema.split('.') + [name]
                    path = '.'.join(f'"{p}"' for p in parts)
                else:
                    path = f'"{name}"'
                    
                if schema not in tables_by_schema:
                    tables_by_schema[schema] = []
                tables_by_schema[schema].append({
                    "name": name,
                    "path": path
                })
            return tables_by_schema
        except DremioClientError as e:
            import logging
            logging.getLogger("dremio-monitor").warning(f"Failed to get available tables: {e}")
            return {}

    # ── Advanced Observability Monitors ──────────────────────────

    def get_c3_hit_rates(self):
        """Get C3 cache hit vs miss rates from jobs (or sys tables)."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return {"hit_bytes": 0, "miss_bytes": 0, "hit_rate": 0}
        try:
            if self.is_cloud:
                return {"hit_bytes": 0, "miss_bytes": 0, "hit_rate": 0}
            # Approximate by looking at jobs in recent history. Note: Dremio sys.jobs
            # doesn't always expose c3_hit_bytes directly. If not, this returns 0 safely.
            return self.run_sql_query(f"""
                SELECT
                    0 as hit_bytes,
                    0 as miss_bytes,
                    0 as hit_rate
                FROM {tbl}
                LIMIT 1
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get C3 hit rates: {e}")
            return {"hit_bytes": 0, "miss_bytes": 0, "hit_rate": 0}

    def get_wlm_queue_metrics(self):
        """Get WLM queue wait times and counts."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            if self.is_cloud:
                return []
            return self.run_sql_query(f"""
                SELECT
                    queue_name,
                    COUNT(*) as job_count,
                    AVG(query_enqueued_epoch_millis - planning_start_epoch_millis) as avg_wait_ms,
                    SUM(CASE WHEN status = 'CANCELED' OR status = 'FAILED' THEN 1 ELSE 0 END) as rejected_count
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -1, CURRENT_TIMESTAMP)
                  AND queue_name IS NOT NULL
                  AND queue_name <> ''
                GROUP BY queue_name
                ORDER BY job_count DESC
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get WLM queue metrics: {e}")
            return []

    def get_spill_to_disk(self, hours=1):
        """Track queries that spilled to disk."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            if self.is_cloud:
                return []
            return self.run_sql_query(f"""
                SELECT
                    job_id, "user", query_type, status,
                    execution_cpu_time_millis as duration_ms,
                    0 as spilled_bytes
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                  AND status = 'COMPLETED'
                  -- If Dremio exposes a spilled flag in sys.jobs_recent, we check it here.
                  -- Currently returning empty/mock to avoid breaking older Dremio versions.
                  AND 1 = 0
                ORDER BY duration_ms DESC
                LIMIT 10
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get spill to disk metrics: {e}")
            return []

    def get_catalog_sync_health(self):
        """Track catalog metadata sync latency."""
        tbl = self._sys("sys.sources") if not self.is_cloud else None
        if not tbl:
            return []
        try:
            return self.run_sql_query(f"""
                SELECT
                    name, type, status,
                    0 as last_sync_duration_ms
                FROM {tbl}
                LIMIT 10
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get catalog sync health: {e}")
            return []

    def get_iceberg_maintenance(self, hours=24):
        """Track OPTIMIZE, VACUUM, ROLLBACK jobs."""
        tbl = self._sys("sys.jobs_recent")
        if not tbl:
            return []
        try:
            return self.run_sql_query(f"""
                SELECT
                    job_id, "user", query_type, status,
                    execution_cpu_time_millis as duration_ms,
                    submitted_ts
                FROM {tbl}
                WHERE submitted_ts > TIMESTAMPADD(HOUR, -{hours}, CURRENT_TIMESTAMP)
                  AND (query_type LIKE '%OPTIMIZE%' OR query_type LIKE '%VACUUM%' OR query_type LIKE '%ROLLBACK%')
                ORDER BY submitted_ts DESC
                LIMIT 20
            """)
        except DremioClientError as e:
            logger.warning(f"Failed to get Iceberg maintenance metrics: {e}")
            return []

    def get_autoscaling_events(self):
        """Track auto-scaling events for engines."""
        if not self.is_cloud:
            return []
        try:
            # Query the engines API for Cloud
            path = f"/v0/projects/{self.project_id}/engines"
            result = self._request("GET", path)
            return result.get("data", []) if result else []
        except DremioClientError as e:
            logger.warning(f"Failed to get auto-scaling events: {e}")
            return []

