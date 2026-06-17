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
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("SUPABASE_DB_URL")

        if not self.database_url:
            raise ValueError(
                "Missing SUPABASE_DB_URL. Please set it in your .env file."
            )

        self.conn = psycopg.connect(self.database_url)
        self.conn.autocommit = True

    def close(self) -> None:
        self.conn.close()

    def insert_raw_market_data(
        self,
        symbol: str,
        row: Dict[str, Any],
    ) -> None:
        """
        Insert one collector row into pionex_raw_market_data.

        row 是 client.flatten_for_db(result) 的結果。
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

        with self.conn.cursor() as cur:
            cur.execute(sql, payload)