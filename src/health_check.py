# src/health_check.py

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

import health_state


PORT = int(os.getenv("PORT", "8000"))
STALE_SEC = int(os.getenv("HEALTH_STALE_SEC", "60"))

NTFY_URL = os.getenv("NTFY_URL", "https://ntfy.sh/crypto-quant-platform-health")
NTFY_TITLE = os.getenv("NTFY_TITLE", "data-collector: service down")
NTFY_PRIORITY = os.getenv("NTFY_PRIORITY", "urgent")


def _send_ntfy(message: str) -> None:
    """Fire-and-forget ntfy notification. Errors are logged but not raised."""
    try:
        resp = requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": NTFY_TITLE,
                "Priority": NTFY_PRIORITY,
                "Tags": "rotating_light,chart_with_downwards_trend",
            },
            timeout=5,
        )
        resp.raise_for_status()
        print(f"[HEALTH] ntfy notification sent HTTP={resp.status_code}", flush=True)
    except Exception as exc:
        print(f"[HEALTH] Failed to send ntfy notification: {exc}", flush=True)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._respond(
                200,
                {
                    "status": "alive",
                    "service": "pionex-collector",
                    "message": "process is running",
                },
            )
            return

        if self.path in ("/health", "/ready"):
            self._handle_ready()
            return

        self._respond(404, {"status": "not_found"})

    def _handle_ready(self) -> None:
        last_fetch, notification_sent = health_state.get_state()
        now = time.time()
        stale_sec = getattr(self.server, "stale_sec", STALE_SEC)

        if last_fetch is None:
            age_sec = None
            is_stale = True
        else:
            age_sec = round(now - last_fetch, 2)
            is_stale = age_sec > stale_sec

        if is_stale:
            body = {
                "status": "stale",
                "last_fetch_age_sec": age_sec,
                "stale_threshold_sec": stale_sec,
            }

            if not notification_sent and health_state.claim_notification():
                age_str = f"{age_sec}s" if age_sec is not None else "never"
                _send_ntfy(
                    "The data-collector process is alive, but no committed "
                    f"database write was recorded. Last success: {age_str} ago."
                )

            self._respond(503, body)
            return

        self._respond(
            200,
            {
                "status": "ready",
                "last_fetch_age_sec": age_sec,
                "stale_threshold_sec": stale_sec,
            },
        )

    def _respond(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN001
        pass


def start_health_server(
    port: int | None = None,
    *,
    stale_sec: int = STALE_SEC,
    return_server: bool = False,
) -> threading.Thread | tuple[HTTPServer, threading.Thread]:
    actual_port = PORT if port is None else port

    server = HTTPServer(("0.0.0.0", actual_port), _HealthHandler)
    server.stale_sec = stale_sec

    thread = threading.Thread(
        target=server.serve_forever,
        name="health-check-server",
        daemon=True,
    )
    thread.start()

    print(f"[HEALTH] Health server listening on port {actual_port}", flush=True)
    print("[HEALTH] Liveness: / | Readiness: /health, /ready", flush=True)

    if return_server:
        return server, thread
    return thread


def run_stale_watchdog(
    stop: threading.Event,
    *,
    stale_sec: float = STALE_SEC,
    check_interval_sec: float = 1.0,
    exit_func=os._exit,
    notifier=None,
    monotonic=time.monotonic,
) -> None:
    """Exit the process when committed DB writes stop advancing.

    This runs outside the collector loop, so a permanently blocked psycopg
    call cannot prevent the watchdog from firing.
    """
    if stale_sec <= 0 or check_interval_sec <= 0:
        raise ValueError("watchdog intervals must be positive")
    notifier = _send_ntfy if notifier is None else notifier
    started_at = monotonic()
    while not stop.wait(check_interval_sec):
        last_success = health_state.get_monotonic_time()
        age_sec = max(
            0.0,
            monotonic() - (
                started_at if last_success is None else last_success
            ),
        )
        if age_sec <= stale_sec:
            continue
        message = (
            "No committed data-collector DB write for "
            f"{age_sec:.1f}s; exiting so Railway can restart the service."
        )
        print(f"[FATAL] {message}", flush=True)
        if health_state.claim_notification():
            notifier(message)
        exit_func(1)
        return


def start_stale_watchdog(
    stop: threading.Event,
    *,
    stale_sec: float = STALE_SEC,
    check_interval_sec: float = 1.0,
) -> threading.Thread:
    thread = threading.Thread(
        target=run_stale_watchdog,
        kwargs={
            "stop": stop,
            "stale_sec": stale_sec,
            "check_interval_sec": check_interval_sec,
        },
        name="db-freshness-watchdog",
        daemon=True,
    )
    thread.start()
    return thread
