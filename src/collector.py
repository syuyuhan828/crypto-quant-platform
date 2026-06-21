# src/collector.py

import time
import json
import os
from typing import Any, Dict, Optional

from Pionex_client import PionexClient, PionexAPIError
from db import SupabaseDB
import health_state
from health_check import start_health_server


class PionexCollector:
    """
    Pionex data collector.

    第一版設計：
    - depth: 每 2 秒
    - trades: 每 2 秒，但和 depth 錯開 1 秒
    - indexes: 每 30 秒
    - open_interests: 每 30 秒，但和 indexes 錯開
    - klines: 每 60 秒
    - funding_rates: 每 600 秒

    儲存格式：
    - JSON Lines: 每一行是一筆 API response
    - 之後可以很容易改成寫入 database
    """

    def __init__(
        self,
        symbol: str = "BTC_USDT_PERP",
        output_dir: str = "data/raw",
        save_to_db: bool = True,
        save_to_jsonl: bool = False,
    ):
        self.symbol = symbol
        self.output_dir = output_dir
        self.client = PionexClient()
        self.save_to_db = save_to_db
        self.db = SupabaseDB() if self.save_to_db else None
        self.save_to_jsonl = save_to_jsonl

        os.makedirs(self.output_dir, exist_ok=True)

        # 每個 API 的抓取設定
        # offset_sec 用來錯開 API，避免同一秒內 weight 太集中
        self.schedule = {
            "depth": {
                "interval_sec": 2.0,
                "offset_sec": 0.0,
                "enabled": True,
            },
            "trades": {
                "interval_sec": 2.0,
                "offset_sec": 1.0,
                "enabled": True,
            },
            "indexes": {
                "interval_sec": 30.0,
                "offset_sec": 10.0,
                "enabled": True,
            },
            "open_interests": {
                "interval_sec": 30.0,
                "offset_sec": 20.0,
                "enabled": True,
            },
            "klines": {
                "interval_sec": 60.0,
                "offset_sec": 30.0,
                "enabled": True,
            },
            "funding_rates": {
                "interval_sec": 600.0,
                "offset_sec": 40.0,
                "enabled": True,
            },
        }

        # 記錄每個 API 上次執行時間
        self.last_run_time = {
            api_name: None for api_name in self.schedule.keys()
        }

        # trades coverage check 需要知道上次抓 trades 的時間
        self.last_trades_fetch_time_ms: Optional[int] = None

    # --------------------------------------------------
    # File helpers
    # --------------------------------------------------

    def get_output_path(self, api_name: str) -> str:
        """
        每個 API 分開存一個 jsonl 檔案。
        """
        filename = f"{self.symbol}_{api_name}.jsonl"
        return os.path.join(self.output_dir, filename)

    def save_jsonl(self, api_name: str, row: Dict[str, Any]) -> None:
        """
        把一筆資料 append 到 jsonl。
        """
        path = self.get_output_path(api_name)

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # --------------------------------------------------
    # Scheduling helpers
    # --------------------------------------------------

    def should_run(self, api_name: str, elapsed_sec: float) -> bool:
        """
        判斷某個 API 這一輪是否應該執行。
        """

        config = self.schedule[api_name]

        if not config["enabled"]:
            return False

        interval = config["interval_sec"]
        offset = config["offset_sec"]
        last_run = self.last_run_time[api_name]

        # 還沒到 offset 前，不執行
        if elapsed_sec < offset:
            return False

        # 第一次執行：時間超過 offset 就可以執行
        if last_run is None:
            return True

        # 後續執行：距離上次執行超過 interval 才執行
        return (time.time() - last_run) >= interval

    def mark_run(self, api_name: str) -> None:
        self.last_run_time[api_name] = time.time()

    # --------------------------------------------------
    # API call handlers
    # --------------------------------------------------

    def fetch_depth(self) -> Dict[str, Any]:
        return self.client.depth(
            symbol=self.symbol,
            limit=1000,
        )

    def fetch_trades(self) -> Dict[str, Any]:
        result = self.client.trades(
            symbol=self.symbol,
            limit=500,
            last_fetch_time_ms=self.last_trades_fetch_time_ms,
        )

        # 這次抓取完成後，更新 last_trades_fetch_time_ms
        self.last_trades_fetch_time_ms = result["meta"]["local_response_time_ms"]

        return result

    def fetch_indexes(self) -> Dict[str, Any]:
        return self.client.indexes(
            symbol=self.symbol,
        )

    def fetch_open_interests(self) -> Dict[str, Any]:
        return self.client.open_interests()

    def fetch_klines(self) -> Dict[str, Any]:
        return self.client.klines(
            symbol=self.symbol,
            interval="1M",
            limit=50,
        )

    def fetch_funding_rates(self) -> Dict[str, Any]:
        return self.client.funding_rates(
            symbol=self.symbol,
            limit=10,
        )

    def fetch_one(self, api_name: str) -> Dict[str, Any]:
        """
        根據 api_name 呼叫對應 fetch function。
        """

        if api_name == "depth":
            return self.fetch_depth()

        if api_name == "trades":
            return self.fetch_trades()

        if api_name == "indexes":
            return self.fetch_indexes()

        if api_name == "open_interests":
            return self.fetch_open_interests()

        if api_name == "klines":
            return self.fetch_klines()

        if api_name == "funding_rates":
            return self.fetch_funding_rates()

        raise ValueError(f"Unknown api_name: {api_name}")

    # --------------------------------------------------
    # Main loop
    # --------------------------------------------------

    def run(self, max_seconds: Optional[int] = None) -> None:
        """
        啟動 collector。

        Args:
            max_seconds:
                None 表示一直跑。
                如果指定秒數，例如 60，代表跑 60 秒後停止。
        """

        # Start the health-check HTTP server in a background thread so
        # Railway (or any external monitor) can poll GET /health.
        start_health_server()

        print("=== Pionex Collector Started ===")
        print(f"symbol: {self.symbol}")
        print(f"output_dir: {self.output_dir}")
        print("schedule:")

        for api_name, config in self.schedule.items():
            if config["enabled"]:
                print(
                    f"  {api_name}: "
                    f"interval={config['interval_sec']}s, "
                    f"offset={config['offset_sec']}s"
                )

        print("Press Ctrl+C to stop.")
        print()

        start_time = time.time()

        while True:
            now = time.time()
            elapsed_sec = now - start_time

            if max_seconds is not None and elapsed_sec >= max_seconds:
                print("Reached max_seconds. Collector stopped.")
                break

            for api_name in self.schedule.keys():
                if not self.should_run(api_name, elapsed_sec):
                    continue

                try:
                    result = self.fetch_one(api_name)

                    # API 成功後立刻標記已執行，避免 DB 壞掉時狂打 API
                    self.mark_run(api_name)

                    # Notify the health-check server that a fetch just succeeded.
                    health_state.record_fetch()

                    db_row = self.client.flatten_for_db(result)

                    if self.save_to_jsonl:
                        self.save_jsonl(api_name, db_row)

                    if self.save_to_db:
                        try:
                            self.db.insert_raw_market_data(
                                symbol=self.symbol,
                                row=db_row,
                            )
                        except Exception as db_error:
                            print(f"[DB ERROR] {api_name}: {type(db_error).__name__}: {db_error}")

                    local_time = result["meta"]["local_response_time_utc"]
                    latency = result["meta"]["latency_ms"]
                    weight = result["meta"]["weight"]

                    print(
                        f"[OK] {local_time} | "
                        f"{api_name} | "
                        f"weight={weight} | "
                        f"latency={latency}ms"
                    )

                    if api_name == "trades" and "trade_coverage" in result:
                        coverage = result["trade_coverage"]
                        if coverage.get("possible_missing_trades") is True:
                            print(
                                "[WARNING] possible missing trades. "
                                "Consider reducing trades interval or using websocket."
                            )
                            print(coverage)

                except PionexAPIError as e:
                    print(f"[API ERROR] {api_name}: {e}")

                    # 如果 rate limit，稍微等久一點
                    if "429" in str(e):
                        print("Rate limited. Sleeping 10 seconds...")
                        time.sleep(10)

                except Exception as e:
                    print(f"[ERROR] {api_name}: {type(e).__name__}: {e}")

            # 小睡一下，避免 while loop 吃滿 CPU
            time.sleep(0.1)


if __name__ == "__main__":
    collector = PionexCollector(
        symbol="BTC_USDT_PERP",
        output_dir="data/raw",
        save_to_db=True,
        save_to_jsonl=False,
    )

    collector.run(max_seconds=None)