# src/health_check.py
#
# Lightweight HTTP health-check server.
#
# Endpoints
# ---------
# GET /health
#   200  {"status": "ok",   "last_fetch_age_sec": <float>}
#   503  {"status": "down", "last_fetch_age_sec": <float|null>}
#
# The server runs in a daemon thread so it never blocks the collector.
# A 503 is returned (and a single ntfy notification is fired) when the
# collector has not completed a successful fetch in the last STALE_SEC
# seconds.

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

import health_state

# ── Configuration ────────────────────────────────────────────────────────────

PORT = 8000
STALE_SEC = 60  # seconds without a fetch before we consider the service down

NTFY_URL = "https://ntfy.sh/crypto-quant-platform-health"
NTFY_TITLE = "data-collector: service down"
NTFY_PRIORITY = "urgent"


# ── ntfy helper ──────────────────────────────────────────────────────────────

def _send_ntfy(message: str) -> None:
    """Fire-and-forget ntfy notification.  Errors are logged but not raised."""
    try:
        resp = requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": NTFY_TITLE,
                "Priority": NTFY_PRIORITY,
                "Tags": "rotating_light,chart_with_downwards_trend",
            },
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[HEALTH] ntfy notification sent (HTTP {resp.status_code})")
    except Exception as exc:
        print(f"[HEALTH] Failed to send ntfy notification: {exc}")


# ── HTTP handler ─────────────────────────────────────────────────────────────

class _HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._respond(404, {"status": "not_found"})
            return

        last_fetch, notification_sent = health_state.get_state()
        now = time.time()

        if last_fetch is None:
            age_sec = None
            is_stale = True
        else:
            age_sec = round(now - last_fetch, 2)
            is_stale = age_sec > STALE_SEC

        if is_stale:
            body = {
                "status": "down",
                "last_fetch_age_sec": age_sec,
                "stale_threshold_sec": STALE_SEC,
            }
            self._respond(503, body)

            # Send at most one ntfy alert per outage window.
            if not notification_sent:
                health_state.mark_notification_sent()
                age_str = f"{age_sec}s" if age_sec is not None else "never"
                _send_ntfy(
                    f"The data-collector service has stopped fetching data. "
                    f"Last successful fetch: {age_str} ago."
                )
        else:
            body = {
                "status": "ok",
                "last_fetch_age_sec": age_sec,
                "stale_threshold_sec": STALE_SEC,
            }
            self._respond(200, body)

    def _respond(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN001
        # Suppress the default per-request stdout noise from BaseHTTPRequestHandler.
        pass


# ── Public API ────────────────────────────────────────────────────────────────

def start_health_server(port: int = PORT) -> threading.Thread:
    """
    Start the health-check HTTP server in a background daemon thread.

    Returns the thread so the caller can join it if needed (though in
    normal operation the thread runs for the lifetime of the process).
    """
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)

    thread = threading.Thread(
        target=server.serve_forever,
        name="health-check-server",
        daemon=True,
    )
    thread.start()
    print(f"[HEALTH] Health check server listening on port {port} → /health")
    return thread
