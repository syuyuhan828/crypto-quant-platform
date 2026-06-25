#research/load_db.py

import os
import json
import pandas as pd
import plotly.express as px
import time
from dotenv import load_dotenv
from supabase import create_client




load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_PROJ_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

RAW_TABLE = "pionex_raw_market_data"




def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("E: Missing SUPABASE_PROJ_URL or SUPABASE_SERVICE_KEY")

    return create_client(SUPABASE_URL, SUPABASE_KEY)


def ensure_dict(x):
    if isinstance(x, dict):
        return x

    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return {}

    return {}

# =============== 
# helper function
# ===============
def safe_float(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


# find 30 mins and 10 second data
def get_latest_table_time_ms():
    supabase = get_supabase()

    resp = (
        supabase
        .table(RAW_TABLE)
        .select("local_response_time_ms")
        .order("local_response_time_ms", desc=True)
        .limit(1)
        .execute()
    )

    rows = resp.data or []

    if not rows: raise ValueError("No data in table")

    return int(rows[0]["local_response_time_ms"])

def get_api_last_minutes(
    api_name,
    minutes=30,
    filtered_min=None,
    page_size=500,
    chunk_minutes=10,
    end_ms=None,
):
    start_time = time.time()
    supabase = get_supabase()

    if filtered_min is None:
        filtered_min = minutes

    if end_ms is None:
        end_ms = get_latest_table_time_ms()

    start_ms = end_ms - minutes * 60 * 1000
    start_filter = end_ms - filtered_min * 60 * 1000
    end_filter = end_ms

    rows_all = []

    chunk_ms = chunk_minutes * 60 * 1000
    chunk_start = start_ms

    while chunk_start < end_ms:
        chunk_end = min(chunk_start + chunk_ms, end_ms)

        cursor = chunk_start - 1

        while True:
            resp = (
                supabase
                .table(RAW_TABLE)
                .select("local_response_time_ms, data")
                .eq("api_name", api_name.strip())
                .gt("local_response_time_ms", cursor)
                .lte("local_response_time_ms", chunk_end)
                .order("local_response_time_ms", desc=False)
                .limit(page_size)
                .execute()
            )

            rows = resp.data or []

            print(
                f"{api_name} chunk "
                f"{pd.to_datetime(chunk_start, unit='ms', utc=True)} "
                f"-> {pd.to_datetime(chunk_end, unit='ms', utc=True)}, "
                f"rows={len(rows)}"
            )

            if not rows:
                break

            rows_all.extend(rows)

            if len(rows) < page_size:
                break

            cursor = int(rows[-1]["local_response_time_ms"])

        chunk_start = chunk_end

    df = pd.DataFrame(rows_all)

    if df.empty:
        print(f"No value in request: {api_name}")
        return df, start_filter, end_filter

    df = (
        df
        .drop_duplicates(subset=["local_response_time_ms"])
        .sort_values("local_response_time_ms")
        .reset_index(drop=True)
    )

    df["local_response_dt"] = pd.to_datetime(
        df["local_response_time_ms"],
        unit="ms",
        utc=True,
    )

    print(
        f"using {time.time() - start_time:.3f}s to fetch result of {api_name}, "
        f"rows={len(df)}"
    )

    return df, start_filter, end_filter

#parse depth table: 
# depth data table example:
# "data": {"bids": [["64864", "33.3354"]], "asks": [["64864.1", "1.629"]]}
def parse_depth_table(df):
    
    # desired output df["bids_diff"]={ "bids": [[tick, diff_amount], [tick, diff_amount]], "updateTime": timestamp}

    # desired output df["asks_diff"]={ "asks": [[tick, diff_amount], [tick, diff_amount]], "updateTime": timestamp}

    rows = []

    prev_bids = {}
    prev_asks = {}

    for _, row in df.iterrows():
        d = row["data"]
        local_time = int(row["local_response_time_ms"])
        exchange_update_time = d.get("updateTime", None)

        bids = {
            float(price): float(price) * float(amount)
            for price, amount in d["bids"]
        }

        asks = {
            float(price): float(price) * float(amount)
            for price, amount in d["asks"]
        }


        bids_diff = []
        for tick in sorted(set(bids) | set(prev_bids), reverse=True):
            if tick in bids and tick in prev_bids:
                diff = bids[tick] - prev_bids[tick]
            else:
                diff = None
            bids_diff.append([tick, diff])


        asks_diff = []
        for tick in sorted(set(asks) | set(prev_asks)):
            if tick in asks and tick in prev_asks:
                diff = asks[tick] - prev_asks[tick]
            else:
                diff = None
            asks_diff.append([tick, diff])
    
        rows.append({
            "local_response_time_ms": local_time,
            "exchange_time": exchange_update_time,
            "bids": bids,
            "asks": asks,
            "bids_diff": bids_diff,
            "asks_diff": asks_diff,
        })

        prev_bids = bids
        prev_asks = asks

    return pd.DataFrame(rows)

# plot the parse_depth_table. x is the tick price had shown, y is the diff_price, with a drag bar that control time
def depth_diff_to_long(df):
    rows = []

    for _, row in df.iterrows():
        t = row["local_response_time_ms"]

        for tick, diff in row['bids_diff']:
            if diff is not None:
                rows.append({
                    "local_response_time_ms": t,
                    "side": "bid",
                    "tick_price": tick,
                    "diff_notional": diff,
                })
        
        for tick, diff in row['asks_diff']:
            if diff is not None:
                rows.append({
                    "local_response_time_ms": t,
                    "side": "ask",
                    "tick_price": tick,
                    "diff_notional": diff,
                })
    return pd.DataFrame(rows)

# plot bids and asks
def plot_depth_diff_slider(df):
    long_df = depth_diff_to_long(df)
    
    x_min = long_df["tick_price"].min()
    x_max = long_df["tick_price"].max()

    y_abs = long_df["diff_notional"].abs().max()

    long_df["updateTime_str"] = pd.to_datetime(
        long_df["local_response_time_ms"],
        unit="ms",
        utc=True,
    ).dt.strftime("%H:%M:%S")

    fig = px.bar(
        long_df,
        x = "tick_price",
        y = "diff_notional",
        color="side",
        animation_frame="updateTime_str",
        barmode="group",
        color_discrete_map={
            "bid": "green",
            "ask": "red",
        },
        title="Depth diff by tick",
        labels={
            "tick_price": "Tick Price",
            "diff_notional": "Diff Notional USDT",
            "side": "Side",
            "updateTime_str": "Timestamp",
        },
    )

    fig.update_layout(
        xaxis = dict(range=[x_min, x_max]),
        yaxis = dict(range=[-y_abs, y_abs]),
        xaxis_title = "Tick Price",
        yaxis_title = "Diff Notional (USDT)",
    )

    fig.show()

def flat_kline(kline, start_ms = None, end_ms = None):

    k = kline.copy()
    rows = []

    for _, row in k.iterrows():
        for d in row["data"]["klines"]:
            rows.append(d)

    df = pd.DataFrame(rows)
    df = (
        df
        .drop_duplicates(subset=['time'], keep='last')
        .sort_values("time")
        .reset_index(drop=True)
    )
    df['local_response_time_ms'] = df['time']

    if start_ms is not None:
        df = df[df["local_response_time_ms"] >= start_ms]
    if end_ms is not None:
        df = df[df["local_response_time_ms"] <= end_ms]
    return df.reset_index(drop=True)



# flat trade data
def flat_trades(trades, start_ms=None, end_ms=None):
    #  {"trades": [{"symbol": "BTC_USDT_PERP", "tradeId": "200000001316248411", "price": "64302.4", "size": "0.2072", "side": "BUY", "timestamp": 1782041128986}]
    rows = []
    seen = set()

    for _, row in trades.iterrows():
        data = row['data']

        for t in data['trades']:
            trade_id = str(t["tradeId"])

            if trade_id in seen:
                continue

            seen.add(trade_id)

            price = float(t["price"])
            size = float(t['size'])
            ts = int(t["timestamp"])

            rows.append({
                "local_response_time_ms": ts,
                "trade_id": trade_id,
                "symbol": t["symbol"],
                "side": t["side"].lower(),
                "price": price,
                "size": size,
                "notional": price * size,
            })
    
    df = pd.DataFrame(rows)

    if df.empty:
        return df
    
    if start_ms is not None:
        df = df[df["local_response_time_ms"] >= start_ms]

    if end_ms is not None:
        df = df[df["local_response_time_ms"] <= end_ms]

    return (
        df
        .sort_values("local_response_time_ms")
        .reset_index(drop=True)
    )

# concatenate klines w/ depth dataframe
def outer_concat_by_time(depth, klines, trades):
    d = depth.copy()
    k = klines.copy()
    t = trades.copy()

    d['type'] = "depth_diff"
    k['type'] = "klines"
    t['type'] = "trades"

    out = pd.concat(
        [d, k, t],
        axis = 0,
        join = "outer",
        ignore_index=True,
    )

    out = (
        out
        .sort_values("local_response_time_ms")
        .reset_index(drop = True)
    )

    return out

# catch trade & depth data within each kline
def get_kline_window(df: pd.DataFrame, kline_idx: int):
    df = df.sort_values("local_response_time_ms").reset_index(drop=True)

    klines = df[df["type"] == "klines"].reset_index(drop=True)

    if kline_idx >= len(klines) - 1:
        raise ValueError("kline_idx is too large. Need kline_idx < len(klines) - 1")
    
    start_ms = int(klines.loc[kline_idx, "local_response_time_ms"])
    end_ms = int(klines.loc[kline_idx + 1, "local_response_time_ms"])

    window = df[
        (df["local_response_time_ms"] >= start_ms) 
        & (df["local_response_time_ms"] <= end_ms)
    ].copy()

    depth_window = window[window["type"] == "depth_diff"].copy()
    trades_window = window[window["type"] == "trades"].copy()
    kline_start = klines.loc[kline_idx].copy()
    kline_end = klines.loc[kline_idx + 1].copy()

    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "kline_start": kline_start,
        "kline_end": kline_end,
        "depth_window": depth_window,
        "trades_window": trades_window,
        "window": window,
    }

#feature of kline window
def book_liquidity(book, side, width=50):
    prices = list(book.keys())

    if side == "bid":
        best = max(prices)
        liq = sum(v for p, v in book.items() if p >= best - width)
    else:
        best = min(prices)
        liq = sum(v for p, v in book.items() if p <= best + width)

    return best, liq


def summarize_kline_window(result, width=50):
    k0 = result["kline_start"]
    k1 = result["kline_end"]

    depth_window = result["depth_window"]
    trades_window = result["trades_window"]

    open_price = float(k0["open"])
    close_price = float(k0["close"])
    high_price = float(k0["high"])
    low_price = float(k0["low"])
    volume = float(k0["volume"])

    return_1m = close_price / open_price - 1

    next_return_1m = (
        float(k1["close"]) / float(k1["open"]) - 1
    )

    # =====================
    # Trades fuel
    # =====================
    buy_volume = trades_window.loc[
        trades_window["side"] == "buy",
        "size"
    ].sum()

    sell_volume = trades_window.loc[
        trades_window["side"] == "sell",
        "size"
    ].sum()

    buy_notional = trades_window.loc[
        trades_window["side"] == "buy",
        "notional"
    ].sum()

    sell_notional = trades_window.loc[
        trades_window["side"] == "sell",
        "notional"
    ].sum()

    total_notional = buy_notional + sell_notional
    net_trade_notional = buy_notional - sell_notional

    trade_imbalance = (
        net_trade_notional / total_notional
        if total_notional != 0
        else 0
    )

    trade_volume_check = buy_volume + sell_volume - volume

    # =====================
    # Start book barrier
    # =====================
    first_depth = depth_window.iloc[0]

    best_bid, bid_liq = book_liquidity(
        first_depth["bids"],
        side="bid",
        width=width,
    )

    best_ask, ask_liq = book_liquidity(
        first_depth["asks"],
        side="ask",
        width=width,
    )

    mid_price = (best_bid + best_ask) / 2
    spread = best_ask - best_bid

    book_imbalance = (
        (bid_liq - ask_liq) / (bid_liq + ask_liq)
        if bid_liq + ask_liq != 0
        else 0
    )

    # =====================
    # Depth diff pressure
    # =====================
    bid_added = 0.0
    bid_removed = 0.0
    ask_added = 0.0
    ask_removed = 0.0

    for _, row in depth_window.iterrows():
        bid_diffs = [x[1] for x in row["bids_diff"] if x[1] is not None]
        ask_diffs = [x[1] for x in row["asks_diff"] if x[1] is not None]

        bid_added += sum(x for x in bid_diffs if x > 0)
        bid_removed += -sum(x for x in bid_diffs if x < 0)

        ask_added += sum(x for x in ask_diffs if x > 0)
        ask_removed += -sum(x for x in ask_diffs if x < 0)

    depth_pressure = (
        bid_added
        + ask_removed
        - ask_added
        - bid_removed
    )

    # =====================
    # Fuel ratios
    # =====================
    buy_fuel = buy_notional / ask_liq if ask_liq != 0 else None
    sell_fuel = sell_notional / bid_liq if bid_liq != 0 else None

    net_fuel = (
        net_trade_notional / (bid_liq + ask_liq)
        if bid_liq + ask_liq != 0
        else None
    )

    # =====================
    # Contaminate
    # =====================
    trade_volume_check = buy_volume + sell_volume - volume

    trade_volume_check_pct = (
        trade_volume_check / volume 
        if volume != 0
        else None
    )

    fine_trade_coverage = (
        abs(trade_volume_check_pct) < 0.01
        if trade_volume_check_pct is not None
        else False
    )

    fine_depth_coverage = len(depth_window) >= 25

    return {
        "start_ms": result["start_ms"],
        "end_ms": result["end_ms"],

        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
        "return_1m": return_1m,
        "next_return_1m": next_return_1m,

        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid_price,
        "spread": spread,

        "bid_liq": bid_liq,
        "ask_liq": ask_liq,
        "book_imbalance": book_imbalance,

        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
        "net_trade_notional": net_trade_notional,
        "trade_imbalance": trade_imbalance,

        "bid_added": bid_added,
        "bid_removed": bid_removed,
        "ask_added": ask_added,
        "ask_removed": ask_removed,
        "depth_pressure": depth_pressure,

        "buy_fuel": buy_fuel,
        "sell_fuel": sell_fuel,
        "net_fuel": net_fuel,

        "depth_rows": len(depth_window),
        "trades_rows": len(trades_window),
        "trade_volume_check": trade_volume_check,

        "fine_coverage": fine_trade_coverage or fine_depth_coverage
    }

def build_feature_df_from_windows(timeline, width=50):
    timeline = (
        timeline
        .sort_values("local_response_time_ms")
        .reset_index(drop=True)
    )

    klines = (
        timeline[timeline["type"] == "klines"]
        .sort_values("local_response_time_ms")
        .reset_index(drop=True)
    )

    rows = []

    for kline_idx in range(len(klines) - 1):
        result = get_kline_window(
            timeline,
            kline_idx=kline_idx,
        )

        depth_window = result["depth_window"]
        trades_window = result["trades_window"]

        if depth_window.empty:
            continue

        if trades_window.empty:
            continue

        row = summarize_kline_window(
            result,
            width=width,
        )

        row["kline_idx"] = kline_idx

        rows.append(row)

    return pd.DataFrame(rows)

if __name__ == "__main__":
    FILTERED = 180 #observed window (train set)
    END_MS = get_latest_table_time_ms()
    DEPTH_OBSERVE = 180
    TRADES_OBSERVE = 180
    KLINES_OBSERVE = 180

    START = time.time()

    depth, start_filter, end_filter = get_api_last_minutes(
        "depth", 
        minutes=DEPTH_OBSERVE, 
        filtered_min=FILTERED,
        page_size = 1000,
        chunk_minutes = 20,
        end_ms = END_MS
        
    )
    trades, _, _ = get_api_last_minutes(
        "trades", 
        minutes=TRADES_OBSERVE, 
        filtered_min=FILTERED,
        page_size = 300,
        chunk_minutes = 10,
        end_ms = END_MS,
    )
    klines, _, _ = get_api_last_minutes(
        "klines", 
        minutes=KLINES_OBSERVE, 
        filtered_min=FILTERED,
        chunk_minutes = 60,
        end_ms = END_MS,
    )


    depth_diff = parse_depth_table(depth)
    flat_klines = flat_kline(
        klines,
        start_ms = start_filter,
        end_ms = end_filter,
    )

    flat_trades_df = flat_trades(
        trades,
        start_ms = start_filter,
        end_ms = end_filter,
    )

    depth_diff_trades_to_klines = outer_concat_by_time(
        depth_diff,
        flat_klines,
        flat_trades_df,
    )

    result = get_kline_window(
        depth_diff_trades_to_klines,
        kline_idx=1,

    )

    feature_df = build_feature_df_from_windows(
        depth_diff_trades_to_klines,
        width = 50,
    )

    END = time.time()

    print(feature_df.head())
    print(feature_df.shape)

    print(f"Fine data coverage: {len(feature_df[feature_df["fine_coverage"] == False])/len(feature_df)}%")
    print(f"Took {END - START}s to run the code.")

    # print("depth:", depth.shape)
    # print("depth_diff:", depth_diff.shape)
    # print("flat_klines:", flat_klines.shape)
    # print("depth_diff_to_klines:", depth_diff_trades_to_klines.shape)

    # print(depth_diff_trades_to_klines[["local_response_time_ms", "type"]].head(50))
    


