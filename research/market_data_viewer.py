import os
import json
from typing import Any, Optional

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_PROJ_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

RAW_TABLE = "pionex_raw_market_data"


def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Missing SUPABASE_URL or SUPABASE_KEY in .env")
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)



@st.cache_data(ttl=3600, show_spinner=True)
def fetch_raw(
    api_name: str,
    page_size: int = 1000,
    max_pages: int = 10,
    order_desc: bool = True,
) -> pd.DataFrame:
    supabase = get_supabase()

    rows_all = []
    start = 0

    for page in range(max_pages):
        end = start + page_size - 1

        response = (
            supabase
            .table("pionex_raw_market_data")
            .select("*")
            .eq("api_name", api_name.strip())
            .order("local_response_time_ms", desc=order_desc)
            .range(start, end)
            .execute()
        )

        rows = response.data or []

        if not rows:
            break

        rows_all.extend(rows)

        if len(rows) < page_size:
            break

        start += page_size

    df = pd.DataFrame(rows_all)

    if not df.empty:
        df["local_response_dt"] = pd.to_datetime(
            df["local_response_time_ms"],
            unit="ms",
            utc=True,
        )

        df = df.sort_values("local_response_time_ms").reset_index(drop=True)

    return df


def ensure_dict(x: Any) -> dict:
    if isinstance(x, dict):
        return x

    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return {}

    return {}


def parse_depth(raw_df: pd.DataFrame, levels: int = 50) -> pd.DataFrame:
    rows = []

    for _, row in raw_df.iterrows():
        data = ensure_dict(row["data"])
        bids = data.get("bids", [])
        asks = data.get("asks", [])

        if not bids or not asks:
            continue

        try:
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])

            bid_size = sum(float(x[1]) for x in bids[:levels])
            ask_size = sum(float(x[1]) for x in asks[:levels])

            denom = bid_size + ask_size
            # order book imbalance
            obi = (bid_size - ask_size) / denom if denom else None

            rows.append({
                "time": row["local_response_dt"],
                "local_response_time_ms": row["local_response_time_ms"],
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid_price": (best_bid + best_ask) / 2,
                "spread": best_ask - best_bid,
                "bid_size": bid_size,
                "ask_size": ask_size,
                f"obi_{levels}": obi,
                "latency_ms": row.get("latency_ms"),
            })

        except Exception:
            continue

    return pd.DataFrame(rows)


def parse_indexes(raw_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in raw_df.iterrows():
        data = ensure_dict(row["data"])
        indexes = data.get("indexes", [])

        if not indexes:
            continue

        item = indexes[0]

        mark = pd.to_numeric(item.get("markPrice"), errors="coerce")
        index = pd.to_numeric(item.get("indexPrice"), errors="coerce")
        funding = pd.to_numeric(item.get("nextFundingRate"), errors="coerce")

        rows.append({
            "time": row["local_response_dt"],
            "exchange_update_time": pd.to_datetime(
                item.get("updateTime"),
                unit="ms",
                utc=True,
                errors="coerce",
            ),
            "mark_price": mark,
            "index_price": index,
            "basis": mark - index,
            "basis_pct": (mark - index) / index if index else None,
            "next_funding_rate": funding,
            "latency_ms": row.get("latency_ms"),
        })

    return pd.DataFrame(rows)


def parse_klines(raw_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in raw_df.iterrows():
        data = ensure_dict(row["data"])
        klines = data.get("klines", [])

        for k in klines:
            rows.append({
                "time": pd.to_datetime(k.get("time"), unit="ms", utc=True, errors="coerce"),
                "collector_time": row["local_response_dt"],
                "open": pd.to_numeric(k.get("open"), errors="coerce"),
                "high": pd.to_numeric(k.get("high"), errors="coerce"),
                "low": pd.to_numeric(k.get("low"), errors="coerce"),
                "close": pd.to_numeric(k.get("close"), errors="coerce"),
                "volume": pd.to_numeric(k.get("volume"), errors="coerce"),
                "latency_ms": row.get("latency_ms"),
            })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = (
            df
            .drop_duplicates(subset=["time"])
            .sort_values("time")
            .reset_index(drop=True)
        )

    return df

def parse_open_interests(raw_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rows = []
    for _, row in raw_df.iterrows():
        data = ensure_dict(row["data"])
        items = data.get("openInterests", [])

        target = None
        for item in items:
            if item.get("symbol") == symbol:
                target = item
                break
        
        if not target:
            continue

        oi = pd.to_numeric(target.get("openInterest"), errors="coerce")

        rows.append({
            "time": row["local_response_dt"],
            "open_interest": oi,
            "latency_ms": row.get("latency_ms"),
        })

    return pd.DataFrame(rows)

def parse_funding_rates(raw_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in raw_df.iterrows():
        data = ensure_dict(row["data"])
        rates = data.get("rates", [])

        for r in rates:
            rows.append({
                "time": pd.to_datetime(r.get("fundingTime"), unit="ms", utc=True, errors="coerce"),
                "collector_time": row["local_response_dt"],
                "funding_rate": pd.to_numeric(r.get("fundingRate"), errors="coerce"),
                "latency_ms": row.get("latency_ms"),
            })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = (
            df
            .drop_duplicates(subset=["time"])
            .sort_values("time")
            .reset_index(drop=True)
        )

    return df


def parse_api(raw_df: pd.DataFrame, api_name: str, symbol: str, levels: int) -> pd.DataFrame:
    if api_name == "depth":
        return parse_depth(raw_df, levels=levels)

    if api_name == "indexes":
        return parse_indexes(raw_df)

    if api_name == "klines":
        return parse_klines(raw_df)

    if api_name == "open_interests":
        return parse_open_interests(raw_df, symbol=symbol)

    if api_name == "funding_rates":
        return parse_funding_rates(raw_df)

    return raw_df

def plot_each_series(
    df: pd.DataFrame,
    time_col: str,
    y_cols: list[str],
    title_prefix: str,
):
    for col in y_cols:
        plot_df = df[[time_col, col]].dropna()

        if plot_df.empty:
            st.warning(f"{col} has no data to plot.")
            continue

        fig = px.line(
            plot_df,
            x=time_col,
            y=col,
            title=f"{title_prefix}: {col}",
        )

        st.plotly_chart(fig, width="stretch")

def main():
    st.set_page_config(page_title="Pionex Raw Market Data Viewer", layout="wide")
    st.title("Pionex Raw Market Data Viewer")

    st.sidebar.header("Settings")
    
    if "query_params" not in st.session_state:
        st.session_state.query_params = {
            "api_name": "depth",
            "page_size": 500,
            "symbol": "BTC_USDT_PERP",
            "max_pages": 1,
            "levels": 50,
            "kline_page_size": 50,
            "kline_max_pages": 1,
            "reload_nonce": 0,
        }

    with st.sidebar.form("query_form"):
        st.header("Query Settings")

        ui_api_name = st.selectbox(
            "api_name",
            ["depth", "indexes", "klines", "open_interests", "funding_rates", "trades"],
            index=["depth", "indexes", "klines", "open_interests", "funding_rates", "trades"].index(
                st.session_state.query_params["api_name"]
            ),
        )

        ui_symbol = st.text_input(
            "Symbol",
            value=st.session_state.query_params.get("symbol", "BTC_USDT_PERP"),
        )

        ui_levels = st.number_input(
            "Depth levels",
            min_value=1,
            max_value=50,
            value=int(st.session_state.query_params["levels"]),
            step=1,
        )

        ui_page_size = st.number_input(
            "Main page size",
            min_value=10,
            max_value=1000,
            value=int(st.session_state.query_params["page_size"]),
            step=10,
            help="For heavy APIs like klines/trades, keep this small.",
        )

        ui_max_pages = st.number_input(
            "Main max pages",
            min_value=1,
            max_value=50,
            value=int(st.session_state.query_params["max_pages"]),
            step=1,
        )

        st.divider()

        ui_kline_page_size = st.number_input(
            "Klines page size",
            min_value=1,
            max_value=200,
            value=int(st.session_state.query_params["kline_page_size"]),
            step=1,
            help="Klines raw rows are heavy because each row contains many candles.",
        )

        ui_kline_max_pages = st.number_input(
            "Klines max pages",
            min_value=1,
            max_value=10,
            value=int(st.session_state.query_params["kline_max_pages"]),
            step=1,
        )

        confirm_reload = st.checkbox("Confirm re-fetch", value=False)

        submitted = st.form_submit_button("Re-fetch")

    if submitted:
        if not confirm_reload:
            st.sidebar.warning("Please check Confirm re-fetch first.")
        else:
            st.cache_data.clear()

            st.session_state.query_params = {
                "api_name": ui_api_name,
                "symbol": ui_symbol.strip() or "BTC_USDT_PERP",
                "page_size": int(ui_page_size),
                "max_pages": int(ui_max_pages),
                "levels": int(ui_levels),
                "kline_page_size": int(ui_kline_page_size),
                "kline_max_pages": int(ui_kline_max_pages),
                "reload_nonce": st.session_state.query_params["reload_nonce"] + 1,
            }

            st.sidebar.success("Query params updated. Data refetched.")
            st.rerun()
    
    params = st.session_state.query_params

    api_name = params["api_name"]
    symbol = params.get("symbol", "BTC_USDT_PERP")
    page_size = int(params["page_size"])
    max_pages = int(params["max_pages"])
    levels = int(params["levels"])
    kline_page_size = int(params["kline_page_size"])
    kline_max_pages = int(params["kline_max_pages"])

    raw_df = fetch_raw(
        api_name=api_name,
        page_size=page_size,
        max_pages=max_pages,
        order_desc=True,
    )

    st.subheader("Raw rows")
    st.write(f"raw rows: {len(raw_df):,}")

    if raw_df.empty:
        st.warning("No raw data found.")
        return

    st.dataframe(raw_df.head(20), width="stretch")

    parsed = parse_api(
        raw_df=raw_df,
        api_name=api_name,
        symbol=symbol,
        levels=int(levels),
    )

    st.subheader("Parsed data")
    st.write(f"parsed rows: {len(parsed):,}")

    if parsed.empty:
        st.warning("Parsed data is empty. The JSON format may be different.")
        return

    st.dataframe(parsed.head(100), width="stretch")

    numeric_cols = parsed.select_dtypes(include="number").columns.tolist()

    if "time" not in parsed.columns:
        st.error("Parsed data has no `time` column.")
        return

    default_y = []

    if api_name == "depth":
        default_y = ["mid_price", f"obi_{int(levels)}", "spread"]
    elif api_name == "indexes":
        default_y = ["mark_price", "index_price", "basis_pct", "next_funding_rate"]
    elif api_name == "klines":
        default_y = ["close", "volume"]
    elif api_name == "open_interests":
        default_y = ["open_interest"]
    elif api_name == "funding_rates":
        default_y = ["funding_rate"]

    default_y = [c for c in default_y if c in numeric_cols]

    y_cols = st.multiselect(
        "Y columns",
        options=numeric_cols,
        default=default_y,
    )

    if not y_cols:
        st.info("Select at least one y column.")
        return

    st.subheader("Selected series charts")

    plot_each_series(
        df=parsed,
        time_col="time",
        y_cols=y_cols,
        title_prefix=api_name,
    )

    st.subheader("Klines price reference")

    try:
        kline_raw_df = fetch_raw(
            api_name="klines",
            page_size=kline_page_size,
            max_pages=kline_max_pages,
            order_desc=True,
        )

        kline_df = parse_klines(kline_raw_df)

        if kline_df.empty:
            st.warning("No klines data found.")
        else:
            st.write(f"klines raw rows: {len(kline_raw_df):,}")
            st.write(f"klines parsed candles: {len(kline_df):,}")

            kline_y_cols = [
                col for col in ["close", "volume", "high", "low", "open"]
                if col in kline_df.columns
            ]

            selected_kline_cols = st.multiselect(
                "Klines Y columns",
                options=kline_y_cols,
                default=[col for col in ["close"] if col in kline_y_cols],
            )

            if selected_kline_cols:
                plot_each_series(
                    df=kline_df,
                    time_col="time",
                    y_cols=selected_kline_cols,
                    title_prefix="klines",
                )

    except Exception as e:
        st.error(f"Failed to fetch or plot klines: {e}")

            

if __name__ == "__main__":
    main()