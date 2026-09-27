"""Regression tests for collector freshness and database recovery."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import urlopen

import psycopg


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import health_state  # noqa: E402
from db import SupabaseDB  # noqa: E402
from health_check import (  # noqa: E402
    start_health_server,
    run_stale_watchdog,
)


def _connection() -> MagicMock:
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection


def test_database_connection_has_timeouts_and_reconnects_after_driver_error():
    first = _connection()
    second = _connection()
    first.cursor.return_value.__enter__.return_value.execute.side_effect = (
        psycopg.OperationalError("connection lost")
    )

    with patch("db.psycopg.connect", side_effect=[first, second]) as connect:
        database = SupabaseDB("postgresql://example.invalid/postgres")
        try:
            try:
                database.insert_raw_market_data(
                    "BTC_USDT_PERP",
                    {
                        "api_name": "depth",
                        "local_response_time_ms": 1,
                    },
                )
            except psycopg.OperationalError:
                pass
            else:
                raise AssertionError("the failed insert must be reported to the caller")

            assert connect.call_count == 2
            assert connect.call_args.kwargs["connect_timeout"] == 5
            assert "statement_timeout=5000" in connect.call_args.kwargs["options"]
            assert connect.call_args.kwargs["keepalives"] == 1
            first.close.assert_called_once()
            assert database.conn is second
        finally:
            database.close()


def test_independent_watchdog_notifies_and_exits_when_db_writes_are_stale():
    health_state.reset_for_tests(epoch_time=100.0, monotonic_time=10.0)
    stop = MagicMock()
    stop.wait.side_effect = [False]
    exits: list[int] = []
    messages: list[str] = []

    run_stale_watchdog(
        stop,
        stale_sec=20,
        check_interval_sec=1,
        exit_func=exits.append,
        notifier=messages.append,
        monotonic=lambda: 31.0,
    )

    assert exits == [1]
    assert len(messages) == 1
    assert "21.0" in messages[0]


def test_ready_endpoint_tracks_committed_database_freshness():
    health_state.reset_for_tests(epoch_time=100.0, monotonic_time=10.0)
    server, worker = start_health_server(port=0, stale_sec=5, return_server=True)
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with patch("health_check.time.time", return_value=100.0), patch(
            "health_check._send_ntfy"
        ):
            with urlopen(base + "/ready", timeout=2) as response:
                assert json.load(response)["status"] == "ready"

            health_state.reset_for_tests(epoch_time=90.0, monotonic_time=0.0)
            try:
                urlopen(base + "/ready", timeout=2)
            except HTTPError as error:
                assert error.code == 503
                assert json.load(error)["status"] == "stale"
            else:
                raise AssertionError("stale readiness must return HTTP 503")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_railway_uses_freshness_readiness_and_failure_restart_policy():
    config = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
    deploy = config["deploy"]
    assert deploy["healthcheckPath"] == "/ready"
    assert deploy["restartPolicyType"] == "ON_FAILURE"
    assert deploy["restartPolicyMaxRetries"] == 10

