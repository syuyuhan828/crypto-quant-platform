# src/db.py

import os
import json
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import psycopg


load_dotenv()


class SupabaseDB:
    """
    Direct PostgreSQL writer for Supabase.

    用途：
    - 把 collector 抓到的 raw market data 寫進 Supabase Postgres。

    Connection handling:
    - Supabase's pooler closes idle connections after a timeout, so a single
      persistent connection will eventually go stale.
    - _is_connection_alive() probes the connection before use.
    - _get_connection() transparently reconnects when the probe fails.
    - insert_raw_market_data() retries once on OperationalError so that a
      connection drop mid-flight doesn't lose a data point.
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("SUPABASE_DB_URL")

        if not self.database_url:
            raise ValueError(
                "Missing SUPABASE_DB_URL. Please set it in your .env file."
            )

        self.conn = psycopg.connect(self.database_url)
        self.conn.autocommit = True

    # --------------------------------------------------
    # Connection helpers
    # --------------------------------------------------

    def _is_connection_alive(self) -> bool:
        """
        Return True if self.conn is open and responsive.

        Checks the psycopg closed flag first (cheap), then sends a
        lightweight SELECT 1 to confirm the server side is still up.
        """
        try:
            if self.conn.closed:
                return False
            # SELECT 1 is the canonical lightweight liveness probe.
            self.conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _get_connection(self) -> psycopg.Connection:
        """
        Return a live connection, reconnecting if the current one is stale.

        The connection is kept as an instance variable so it is reused across
        calls when healthy, matching the original single-connection pattern.
        """
        if not self._is_connection_alive():
            print("[DB] Connection is stale — reconnecting...")
            try:
                self.conn.close()
            except Exception:
                pass  # already dead; ignore close errors
            self.conn = psycopg.connect(self.database_url)
            self.conn.autocommit = True
            print("[DB] Reconnected successfully.")
        return self.conn

    def close(self) -> None:
        self.conn.close()

    # --------------------------------------------------
    # Writes
    # --------------------------------------------------

    def insert_raw_market_data(
        self,
        symbol: str,
        row: Dict[str, Any],
    ) -> None:
        """
        Insert one collector row into pionex_raw_market_data.

        row 是 client.flatten_for_db(result) 的結果。

        Retries once on OperationalError (e.g. "the connection is closed")
        by forcing a reconnect before the second attempt so that a pooler
        timeout mid-flight doesn't silently drop a data point.
        """

        sql = """
        insert into pionex_raw_market_data (
            symbol,
            api_name,
            local_request_time_ms,
            local_request_time_utc,
            local_response_time_ms,
            local_response_time_utc,
            api_response_timestamp,
            api_response_time_utc,
            latency_ms,
            weight,
            params,
            data,
            raw,
            trade_coverage
        )
        values (
            %(symbol)s,
            %(api_name)s,
            %(local_request_time_ms)s,
            %(local_request_time_utc)s,
            %(local_response_time_ms)s,
            %(local_response_time_utc)s,
            %(api_response_timestamp)s,
            %(api_response_time_utc)s,
            %(latency_ms)s,
            %(weight)s,
            %(params)s::jsonb,
            %(data)s::jsonb,
            %(raw)s::jsonb,
            %(trade_coverage)s::jsonb
        );
        """

        payload = {
            "symbol": symbol,
            "api_name": row.get("api_name"),
            "local_request_time_ms": row.get("local_request_time_ms"),
            "local_request_time_utc": row.get("local_request_time_utc"),
            "local_response_time_ms": row.get("local_response_time_ms"),
            "local_response_time_utc": row.get("local_response_time_utc"),
            "api_response_timestamp": row.get("api_response_timestamp"),
            "api_response_time_utc": row.get("api_response_time_utc"),
            "latency_ms": row.get("latency_ms"),
            "weight": row.get("weight"),
            "params": json.dumps(row.get("params"), ensure_ascii=False),
            "data": json.dumps(row.get("data"), ensure_ascii=False),
            "raw": json.dumps(row.get("raw"), ensure_ascii=False),
            "trade_coverage": json.dumps(row.get("trade_coverage"), ensure_ascii=False)
            if row.get("trade_coverage") is not None
            else None,
        }

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                conn = self._get_connection()
                with conn.cursor() as cur:
                    cur.execute(sql, payload)
                return  # success — exit early
            except psycopg.OperationalError as exc:
                if attempt < max_attempts:
                    print(
                        f"[DB] OperationalError on attempt {attempt} "
                        f"({exc}) — forcing reconnect and retrying..."
                    )
                    # Force _get_connection() to open a fresh connection on
                    # the next iteration by marking the current one as dead.
                    try:
                        self.conn.close()
                    except Exception:
                        pass
                else:
                    # Both attempts failed — re-raise so the caller can log it.
                    raise