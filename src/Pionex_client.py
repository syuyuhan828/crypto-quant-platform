# src/Pionex_client.py

import time
import requests
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List


class PionexAPIError(Exception):
    """Pionex API error."""
    pass


class PionexClient:
    """
    Pionex public futures API client.

    功能：
    1. 用 API 名稱呼叫 Pionex public futures API
    2. 自動加上本機 request / response 時間
    3. 自動計算 latency
    4. 加入 endpoint weight 與 default limit
    5. 回傳統一格式，方便之後寫入資料庫
    6. 對 recent trades 做 coverage check，判斷是否可能漏成交
    """

    def __init__(self, base_url: str = "https://api.pionex.com", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

        self.endpoints = {
            "depth": "/api/v1/market/depth",
            "trades": "/api/v1/market/trades",
            "klines": "/api/v1/market/klines",
            "book_ticker": "/api/v1/market/bookTicker",
            "indexes": "/api/v1/market/indexes",
            "funding_rates": "/api/v1/market/fundingRates",
            "open_interests": "/api/v1/market/openInterests",
        }

        # Pionex Futures market endpoints 多數 weight = 5
        self.weights = {
            "depth": 5,
            "trades": 5,
            "klines": 5,
            "book_ticker": 5,
            "indexes": 5,
            "funding_rates": 5,
            "open_interests": 5,
        }

        # 第一版資料收集建議 limit
        self.default_limits = {
            "depth": 50,
            "trades": 500,
            "klines": 500,
            "funding_rates": 100,
        }

        # Pionex IP-based limit: 10 weight / second
        self.weight_limit_per_second = 10

    # --------------------------------------------------
    # Time helpers
    # --------------------------------------------------

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def ms_to_utc(ms: Optional[int]) -> Optional[str]:
        if ms is None:
            return None

        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

    # --------------------------------------------------
    # Core request function
    # --------------------------------------------------

    def request(
        self,
        api_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Base API caller.

        Example:
            client.request("depth", {"symbol": "BTC_USDT_PERP", "limit": 50})
            client.request("trades", {"symbol": "BTC_USDT_PERP", "limit": 500})
            client.request("open_interests")
        """

        if api_name not in self.endpoints:
            available = ", ".join(self.endpoints.keys())
            raise ValueError(
                f"Unknown api_name: {api_name}. Available APIs: {available}"
            )

        path = self.endpoints[api_name]
        url = self.base_url + path
        params = params or {}

        local_request_time_ms = self.now_ms()

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise PionexAPIError(f"Request failed: {e}") from e

        local_response_time_ms = self.now_ms()

        try:
            raw = response.json()
        except ValueError as e:
            raise PionexAPIError(
                f"Response is not JSON. "
                f"Status={response.status_code}, "
                f"Text={response.text[:300]}"
            ) from e

        if response.status_code == 429:
            raise PionexAPIError(
                "HTTP 429: Rate limit exceeded. "
                "You are calling the API too frequently."
            )

        if response.status_code != 200:
            raise PionexAPIError(
                f"HTTP error. Status={response.status_code}, Response={raw}"
            )

        if raw.get("result") is False:
            raise PionexAPIError(f"Pionex API returned error: {raw}")

        return self._build_response(
            api_name=api_name,
            url=url,
            params=params,
            local_request_time_ms=local_request_time_ms,
            local_response_time_ms=local_response_time_ms,
            raw=raw,
        )

    # --------------------------------------------------
    # Response wrapper
    # --------------------------------------------------

    def _build_response(
        self,
        api_name: str,
        url: str,
        params: Dict[str, Any],
        local_request_time_ms: int,
        local_response_time_ms: int,
        raw: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        統一整理 API 回傳格式。

        這個格式之後可以直接拿去寫資料庫。
        """

        api_timestamp = raw.get("timestamp")
        weight = self.weights.get(api_name)

        meta = {
            "api_name": api_name,
            "url": url,
            "params": params,
            "weight": weight,
            "local_request_time_ms": local_request_time_ms,
            "local_request_time_utc": self.ms_to_utc(local_request_time_ms),
            "local_response_time_ms": local_response_time_ms,
            "local_response_time_utc": self.ms_to_utc(local_response_time_ms),
            "latency_ms": local_response_time_ms - local_request_time_ms,
            "api_response_timestamp": api_timestamp,
            "api_response_time_utc": self.ms_to_utc(api_timestamp),
        }

        response = {
            "meta": meta,
            "data": raw.get("data")
        }

        return response

    # --------------------------------------------------
    # Convenience methods
    # --------------------------------------------------

    def depth(
        self,
        symbol: str = "BTC_USDT_PERP",
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Order book snapshot.

        建議：
            limit = 50

        可用來算：
            top 1 / 5 / 10 / 20 / 50 order book imbalance
        """

        if limit is None:
            limit = self.default_limits["depth"]

        return self.request(
            "depth",
            {
                "symbol": symbol,
                "limit": limit,
            },
        )

    def trades(
        self,
        symbol: str = "BTC_USDT_PERP",
        limit: Optional[int] = None,
        last_fetch_time_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Recent taker-side trades.

        建議：
            limit = 500

        如果有傳入 last_fetch_time_ms，
        會自動檢查這次 recent trades 是否覆蓋到上次抓取時間。
        """

        if limit is None:
            limit = self.default_limits["trades"]

        response = self.request(
            "trades",
            {
                "symbol": symbol,
                "limit": limit,
            },
        )

        if last_fetch_time_ms is not None:
            response["trade_coverage"] = self.check_trade_coverage(
                response=response,
                last_fetch_time_ms=last_fetch_time_ms,
            )

        return response

    def klines(
        self,
        symbol: str = "BTC_USDT_PERP",
        interval: str = "1M",
        limit: Optional[int] = None,
        end_time_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Kline data.

        建議：
            interval = "1M"
            limit = 500

        覆蓋時間：
            coverage = interval * limit
        """

        if limit is None:
            limit = self.default_limits["klines"]

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        if end_time_ms is not None:
            params["endTime"] = end_time_ms

        return self.request("klines", params)

    def book_ticker(
        self,
        symbol: str = "BTC_USDT_PERP",
    ) -> Dict[str, Any]:
        """
        Best bid / ask snapshot.
        """

        return self.request(
            "book_ticker",
            {
                "symbol": symbol,
            },
        )

    def indexes(
        self,
        symbol: str = "BTC_USDT_PERP",
    ) -> Dict[str, Any]:
        """
        Index price, mark price, next funding rate.
        """

        return self.request(
            "indexes",
            {
                "symbol": symbol,
            },
        )

    def funding_rates(
        self,
        symbol: str = "BTC_USDT_PERP",
        limit: Optional[int] = None,
        end_time_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Historical funding rates.

        建議：
            limit = 100

        做歷史回補時可以改成 500。
        """

        if limit is None:
            limit = self.default_limits["funding_rates"]

        params = {
            "symbol": symbol,
            "limit": limit,
        }

        if end_time_ms is not None:
            params["endTime"] = end_time_ms

        return self.request("funding_rates", params)

    def open_interests(self) -> Dict[str, Any]:
        """
        Current open interests for all futures symbols.

        注意：
            這是 snapshot，沒有時間範圍。
            要靠 local_response_time_ms 記錄你抓到這筆資料的時間。
        """

        return self.request("open_interests")

    # --------------------------------------------------
    # Rate limit helper
    # --------------------------------------------------

    def estimate_cycle_weight(self, api_names: List[str]) -> Dict[str, Any]:
        """
        估算一輪 API calls 會消耗多少 weight。

        Example:
            client.estimate_cycle_weight(["depth", "trades", "indexes"])
        """

        total_weight = 0
        detail = {}

        for name in api_names:
            if name not in self.weights:
                raise ValueError(f"Unknown api name for weight: {name}")

            w = self.weights[name]
            detail[name] = w
            total_weight += w

        theoretical_min_interval_sec = total_weight / self.weight_limit_per_second

        return {
            "detail": detail,
            "total_weight": total_weight,
            "weight_limit_per_second": self.weight_limit_per_second,
            "theoretical_min_interval_sec": theoretical_min_interval_sec,
            "recommended_interval_sec": theoretical_min_interval_sec * 1.5,
        }

    # --------------------------------------------------
    # Coverage check
    # --------------------------------------------------

    def check_trade_coverage(
        self,
        response: Dict[str, Any],
        last_fetch_time_ms: int,
    ) -> Dict[str, Any]:
        """
        檢查 recent trades 是否可能漏資料。

        邏輯：
            如果這次拿到的最舊 trade timestamp 仍然比 last_fetch_time_ms 還新，
            代表上次抓取時間到這次最舊 trade 中間可能有資料沒拿到。

        condition:
            oldest_trade_time_ms > last_fetch_time_ms
            => possible_missing_trades = True
        """

        data = response.get("data") or {}
        trades = data.get("trades") or []

        if not trades:
            return {
                "has_trades": False,
                "last_fetch_time_ms": last_fetch_time_ms,
                "last_fetch_time_utc": self.ms_to_utc(last_fetch_time_ms),
                "possible_missing_trades": None,
                "reason": "No trades returned.",
            }

        timestamps = []

        for trade in trades:
            ts = trade.get("timestamp")
            if ts is not None:
                try:
                    timestamps.append(int(ts))
                except ValueError:
                    pass

        if not timestamps:
            return {
                "has_trades": True,
                "last_fetch_time_ms": last_fetch_time_ms,
                "last_fetch_time_utc": self.ms_to_utc(last_fetch_time_ms),
                "possible_missing_trades": None,
                "reason": "Trades returned but no valid timestamp field found.",
            }

        newest_trade_time_ms = max(timestamps)
        oldest_trade_time_ms = min(timestamps)

        possible_missing = oldest_trade_time_ms > last_fetch_time_ms

        return {
            "has_trades": True,
            "trade_count": len(trades),
            "newest_trade_time_ms": newest_trade_time_ms,
            "newest_trade_time_utc": self.ms_to_utc(newest_trade_time_ms),
            "oldest_trade_time_ms": oldest_trade_time_ms,
            "oldest_trade_time_utc": self.ms_to_utc(oldest_trade_time_ms),
            "last_fetch_time_ms": last_fetch_time_ms,
            "last_fetch_time_utc": self.ms_to_utc(last_fetch_time_ms),
            "covered_since_last_fetch": not possible_missing,
            "possible_missing_trades": possible_missing,
        }

    # --------------------------------------------------
    # Database-friendly flatten function
    # --------------------------------------------------

    def flatten_for_db(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        把 response 整理成資料庫比較好存的格式。

        建議資料庫欄位：
            api_name
            params
            weight
            local_request_time_ms
            local_response_time_ms
            latency_ms
            api_response_timestamp
            data_json
            raw_json
        """

        meta = response["meta"]

        row = {
            "api_name": meta["api_name"],
            "url": meta["url"],
            "params": meta["params"],
            "weight": meta["weight"],
            "local_request_time_ms": meta["local_request_time_ms"],
            "local_request_time_utc": meta["local_request_time_utc"],
            "local_response_time_ms": meta["local_response_time_ms"],
            "local_response_time_utc": meta["local_response_time_utc"],
            "latency_ms": meta["latency_ms"],
            "api_response_timestamp": meta["api_response_timestamp"],
            "api_response_time_utc": meta["api_response_time_utc"],
            "data": response["data"],
        }

        if "trade_coverage" in response:
            row["trade_coverage"] = response["trade_coverage"]

        return row


# --------------------------------------------------
# Local test
# --------------------------------------------------

if __name__ == "__main__":
    client = PionexClient()

    print("=== Weight Estimate ===")
    estimate = client.estimate_cycle_weight(
        ["depth", "trades", "indexes", "open_interests"]
    )
    print(estimate)

    print("\n=== Depth Test ===")
    depth_result = client.depth(
        symbol="BTC_USDT_PERP",
        limit=50,
    )
    print(depth_result["meta"])
    print(depth_result["data"])

    print("\n=== Trades Test ===")
    # 第一次沒有 last_fetch_time，所以先單純抓
    trades_result = client.trades(
        symbol="BTC_USDT_PERP",
        limit=500,
    )
    print(trades_result["meta"])
    print(trades_result["data"])

    print("\n=== Flatten Example ===")
    db_row = client.flatten_for_db(depth_result)
    print(db_row.keys())

    #each second 171kb