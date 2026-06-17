# src/health_state.py
#
# Shared state between the collector and the health check server.
# Both modules import this module directly so they operate on the
# same in-process objects.

import threading

# Protects all mutable fields below.
_lock = threading.Lock()

# Epoch timestamp (float, seconds) of the most recent successful API
# fetch.  None means the collector has not completed a single fetch yet.
last_fetch_time: float | None = None

# Flipped to True the first time a 503 notification is sent so we do
# not spam ntfy on every subsequent health-check poll.
notification_sent: bool = False


def record_fetch() -> None:
    """Call this after every successful API fetch."""
    import time

    global last_fetch_time, notification_sent
    with _lock:
        last_fetch_time = time.time()
        # Reset the flag so a future outage will trigger a new alert.
        notification_sent = False


def get_state() -> tuple[float | None, bool]:
    """Return (last_fetch_time, notification_sent) atomically."""
    with _lock:
        return last_fetch_time, notification_sent


def mark_notification_sent() -> None:
    global notification_sent
    with _lock:
        notification_sent = True
