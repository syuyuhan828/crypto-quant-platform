# src/health_state.py
#
# Shared state between the collector and the health check server.
# Both modules import this module directly so they operate on the
# same in-process objects.

import threading
import time

# Protects all mutable fields below.
_lock = threading.Lock()

# Epoch timestamp (float, seconds) of the most recent successful API
# fetch.  None means the collector has not completed a single fetch yet.
last_fetch_time: float | None = None

# Monotonic clock for watchdog decisions. Unlike wall-clock time this cannot
# jump backwards when the host clock is corrected.
last_fetch_monotonic: float | None = None

# Flipped to True the first time a 503 notification is sent so we do
# not spam ntfy on every subsequent health-check poll.
notification_sent: bool = False


def record_fetch(
    *, epoch_time: float | None = None, monotonic_time: float | None = None
) -> None:
    """Record a successfully committed collector row."""
    global last_fetch_time, last_fetch_monotonic, notification_sent
    with _lock:
        last_fetch_time = time.time() if epoch_time is None else epoch_time
        last_fetch_monotonic = (
            time.monotonic() if monotonic_time is None else monotonic_time
        )
        # Reset the flag so a future outage will trigger a new alert.
        notification_sent = False


def get_state() -> tuple[float | None, bool]:
    """Return (last_fetch_time, notification_sent) atomically."""
    with _lock:
        return last_fetch_time, notification_sent


def get_monotonic_time() -> float | None:
    """Return the last successful commit time on the monotonic clock."""
    with _lock:
        return last_fetch_monotonic


def mark_notification_sent() -> None:
    global notification_sent
    with _lock:
        notification_sent = True


def claim_notification() -> bool:
    """Atomically claim the one notification allowed for this outage."""
    global notification_sent
    with _lock:
        if notification_sent:
            return False
        notification_sent = True
        return True


def reset_for_tests(*, epoch_time: float, monotonic_time: float) -> None:
    """Reset state deterministically; intended for tests only."""
    global last_fetch_time, last_fetch_monotonic, notification_sent
    with _lock:
        last_fetch_time = epoch_time
        last_fetch_monotonic = monotonic_time
        notification_sent = False
