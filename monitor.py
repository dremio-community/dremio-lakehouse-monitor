#!/usr/bin/env python3
"""
Dremio Lakehouse Monitor — Main Server
Real-time monitoring, diagnostics, and alerting for Dremio.

Usage:
    python3 monitor.py [--port 8770] [--host 0.0.0.0]
"""

import argparse
import hashlib
import http.server
import json
import logging
import os
import struct
import urllib.parse
import sys
import threading
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from lib import db
from lib.poller import Poller
from lib.alert_engine import AlertEngine
from lib.notifiers import Notifier

# ── Logging ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("dremio-monitor")

# ── Globals ──────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
WS_CLIENTS = set()
WS_LOCK = threading.Lock()

poller = None
alert_engine = None
notifier = None


# ── WebSocket Helpers (RFC 6455) ─────────────────────────────────

def ws_handshake(handler):
    """Perform WebSocket upgrade handshake."""
    key = handler.headers.get("Sec-WebSocket-Key", "")
    accept = hashlib.sha1(
        (key + "258EAFA5-E914-47DA-95CA-5AB5DC799073").encode()
    ).digest()
    import base64
    accept_b64 = base64.b64encode(accept).decode()
    handler.send_response(101)
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept_b64)
    handler.end_headers()


def ws_read_frame(sock):
    """Read a WebSocket frame. Returns (opcode, payload) or (None, None)."""
    try:
        header = sock.recv(2)
        if len(header) < 2:
            return None, None
        opcode = header[0] & 0x0F
        masked = header[1] & 0x80
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", sock.recv(8))[0]
        mask = sock.recv(4) if masked else None
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None, None
            data += chunk
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return opcode, data
    except Exception:
        return None, None


def ws_send_frame(sock, data, opcode=0x01):
    """Send a WebSocket text frame."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    frame = bytearray()
    frame.append(0x80 | opcode)
    length = len(data)
    if length < 126:
        frame.append(length)
    elif length < 65536:
        frame.append(126)
        frame.extend(struct.pack(">H", length))
    else:
        frame.append(127)
        frame.extend(struct.pack(">Q", length))
    frame.extend(data)
    try:
        sock.sendall(frame)
    except Exception:
        pass


def ws_push_all(event_type, data):
    """Push an event to all connected WebSocket clients."""
    message = json.dumps({"type": event_type, "data": data}, default=str)
    dead = set()
    with WS_LOCK:
        for client_sock in WS_CLIENTS:
            try:
                ws_send_frame(client_sock, message)
            except Exception:
                dead.add(client_sock)
        WS_CLIENTS.difference_update(dead)


# ── HTTP Request Handler ────────────────────────────────────────

class MonitorHandler(http.server.BaseHTTPRequestHandler):
    """HTTP and WebSocket request handler."""

    def log_message(self, format, *args):
        # Suppress default HTTP logs for cleaner output
        if "/ws" not in str(args[0]) and "/api/" not in str(args[0]):
            logger.debug(format % args)

    def do_GET(self):
        path = self.path.split("?")[0]

        # WebSocket upgrade
        if path == "/ws":
            self._handle_websocket()
            return

        # API endpoints
        if path.startswith("/api/"):
            self._handle_api_get(path)
            return

        # Static files
        self._serve_static(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            self._handle_api_post(path)
            return
        self._send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            self._handle_api_delete(path)
            return
        self._send_json({"error": "Not found"}, 404)

    # ── API GET Handlers ─────────────────────────────────────────

    def _handle_api_get(self, path):
        global poller
        if path == "/api/status":
            if poller:
                self._send_json(poller.get_dashboard_summary())
            else:
                self._send_json({"connected": False, "error": "No connection configured"})

        elif path == "/api/jobs/active":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("active_jobs", []))

        elif path == "/api/jobs/recent":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("recent_jobs", []))

        elif path == "/api/reflections":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("reflections", []))

        elif path == "/api/memory":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("memory", []))

        elif path == "/api/sources":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("sources", []))

        elif path == "/api/alerts/history":
            self._send_json(db.get_alert_history())

        elif path == "/api/alerts/rules":
            self._send_json(db.get_alert_rules())

        elif path == "/api/connections":
            profiles = db.get_connection_profiles()
            # Redact passwords
            for p in profiles:
                if p.get("password"):
                    p["password"] = "••••••••"
                if p.get("pat_token"):
                    p["pat_token"] = p["pat_token"][:8] + "••••••••"
            self._send_json(profiles)

        elif path == "/api/notifications":
            self._send_json(db.get_all_notification_configs())

        elif path.startswith("/api/snapshots"):
            hours = 1
            if "?" in self.path:
                params = urllib.parse.parse_qs(self.path.split("?")[1])
                hours = int(params.get("hours", [1])[0])
            self._send_json(db.get_query_snapshots(hours))

        elif path == "/api/top-users":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("top_users", []))

        elif path == "/api/top-datasets":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("top_datasets", []))

        elif path == "/api/duration-distribution":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("duration_distribution", {}))

        elif path == "/api/success-breakdown":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("success_breakdown", {}))

        elif path == "/api/query-lifecycle":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("query_lifecycle", {}))

        elif path == "/api/error-patterns":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("error_patterns", []))

        elif path == "/api/query-types":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("query_types", []))

        elif path == "/api/scan-efficiency":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("scan_efficiency", {}))

        elif path == "/api/reflection-efficiency":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("reflection_efficiency", []))

        elif path == "/api/engine-health":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("engine_health", {}))

        elif path == "/api/engine-history":
            hours = 4
            if "?" in self.path:
                params = urllib.parse.parse_qs(self.path.split("?")[1])
                hours = int(params.get("hours", [4])[0])
            self._send_json(db.get_engine_snapshots(hours))

        elif path == "/api/reflection-health":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("reflection_health", {}))

        elif path == "/api/reflection-history":
            hours = 4
            if "?" in self.path:
                params = urllib.parse.parse_qs(self.path.split("?")[1])
                hours = int(params.get("hours", [4])[0])
            self._send_json(db.get_reflection_snapshots(hours))

        elif path == "/api/watched-tables":
            self._send_json(db.get_watched_tables())

        elif path == "/api/available-tables":
            if poller and poller.client:
                tables = poller.client.get_available_tables()
                self._send_json(tables)
            else:
                self._send_json({"error": "Not connected"}, 500)

        elif path == "/api/iceberg-health":
            state = poller.get_state() if poller else {}
            self._send_json(state.get("iceberg_health", []))

        elif path == "/api/dashboard-layout":
            layout = db.get_dashboard_layout()
            self._send_json(layout)

        else:
            self._send_json({"error": "Unknown endpoint"}, 404)

    # ── API POST Handlers ────────────────────────────────────────

    def _handle_api_post(self, path):
        global poller, alert_engine
        body = self._read_body()

        if path == "/api/connection":
            db.save_connection_profile(body)
            success, msg = poller.configure(body) if poller else (False, "Poller not initialized")
            self._send_json({"success": success, "message": msg})

        elif path == "/api/connection/test":
            from lib.dremio_client import DremioClient
            client = DremioClient(body)
            success, msg = client.test_connection()
            self._send_json({"success": success, "message": msg})

        elif path == "/api/alerts/rules":
            rule_id = db.save_alert_rule(body)
            self._send_json({"success": True, "id": rule_id})

        elif path == "/api/alerts/toggle":
            db.toggle_alert_rule(body.get("id"), body.get("enabled", True))
            self._send_json({"success": True})

        elif path == "/api/alerts/acknowledge":
            db.acknowledge_alert(body.get("id"))
            self._send_json({"success": True})

        elif path == "/api/notifications":
            db.save_notification_config(
                body.get("channel"), body.get("config", {}), body.get("enabled", True))
            self._send_json({"success": True})

        elif path == "/api/notifications/test":
            try:
                notifier.send_test(body.get("channel", "webhook"))
                self._send_json({"success": True, "message": "Test sent"})
            except Exception as e:
                self._send_json({"success": False, "message": str(e)})

        elif path == "/api/dashboard-layout":
            db.save_dashboard_layout(body)
            self._send_json({"success": True})

        elif path == "/api/watched-tables":
            db.save_watched_table(
                body.get("table_path", ""),
                body.get("label"))
            self._send_json({"success": True})

        else:
            self._send_json({"error": "Unknown endpoint"}, 404)

    # ── API DELETE Handlers ──────────────────────────────────────

    def _handle_api_delete(self, path):
        if path.startswith("/api/alerts/rules/"):
            rule_id = int(path.split("/")[-1])
            db.delete_alert_rule(rule_id)
            self._send_json({"success": True})
        elif path.startswith("/api/connections/"):
            name = urllib.parse.unquote(path.split("/")[-1])
            db.delete_connection_profile(name)
            self._send_json({"success": True})
        elif path.startswith("/api/watched-tables/"):
            table_id = int(path.split("/")[-1])
            db.delete_watched_table(table_id)
            self._send_json({"success": True})
        else:
            self._send_json({"error": "Not found"}, 404)

    # ── WebSocket Handler ────────────────────────────────────────

    def _handle_websocket(self):
        ws_handshake(self)
        sock = self.request
        with WS_LOCK:
            WS_CLIENTS.add(sock)
        logger.info(f"WebSocket client connected ({len(WS_CLIENTS)} total)")
        try:
            while True:
                opcode, data = ws_read_frame(sock)
                if opcode is None or opcode == 0x08:
                    break
                if opcode == 0x09:  # Ping
                    ws_send_frame(sock, data, 0x0A)
        except Exception:
            pass
        finally:
            with WS_LOCK:
                WS_CLIENTS.discard(sock)
            logger.info(f"WebSocket client disconnected ({len(WS_CLIENTS)} total)")

    # ── Static File Server ───────────────────────────────────────

    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        file_path = STATIC_DIR / path.lstrip("/")
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        content_types = {
            ".html": "text/html", ".css": "text/css", ".js": "application/javascript",
            ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png",
            ".ico": "image/x-icon",
        }
        ext = file_path.suffix.lower()
        ct = content_types.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", f"{ct}; charset=utf-8" if ext in (".html", ".css", ".js") else ct)
        self.send_header("Cache-Control", "no-cache" if ext in (".html", ".js", ".css") else "max-age=3600")
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    # ── Helpers ──────────────────────────────────────────────────

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body) if body else {}


# ── Alert Evaluation Loop ────────────────────────────────────────

def alert_loop():
    """Background thread that evaluates alerts every 30 seconds."""
    global poller, alert_engine
    while True:
        time.sleep(30)
        if poller and poller.state.get("connected"):
            try:
                triggered = alert_engine.evaluate(poller.get_state())
                if triggered:
                    ws_push_all("alerts", [a for a in triggered])
            except Exception as e:
                logger.error(f"Alert evaluation error: {e}")


# ── Main ─────────────────────────────────────────────────────────

def main():
    global poller, alert_engine, notifier

    parser = argparse.ArgumentParser(description="Lakehouse Monitor for Dremio")
    parser.add_argument("--port", type=int, default=8770, help="Server port (default: 8770)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    args = parser.parse_args()

    import urllib.parse  # noqa - needed for handler

    # Initialize database
    db.init_db()

    # Initialize components
    notifier = Notifier()
    alert_engine = AlertEngine(notifier=notifier)
    poller = Poller(push_callback=ws_push_all)
    poller.start()

    # Auto-connect if default profile exists
    default_profile = db.get_default_profile()
    if default_profile:
        logger.info(f"Auto-connecting with profile: {default_profile['name']}")
        poller.configure(default_profile)

    # Start alert evaluation thread
    alert_thread = threading.Thread(target=alert_loop, daemon=True)
    alert_thread.start()

    # Start HTTP server
    server = http.server.HTTPServer((args.host, args.port), MonitorHandler)
    server.timeout = None

    url = f"http://{args.host}:{args.port}"
    print(f"""
╔══════════════════════════════════════════════════╗
║        Lakehouse Monitor for Dremio              ║
║──────────────────────────────────────────────────║
║  Running at: {url:<35s}║
║  Press Ctrl+C to stop                            ║
╚══════════════════════════════════════════════════╝
""")

    # Try to open browser
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        poller.stop()
        server.server_close()


if __name__ == "__main__":
    main()
