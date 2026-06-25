import os
import json
import pandas as pd
import plotly.express as px
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import statsmodels.api as sm

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_PROJ_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

RAW_TABLE = "pionex_raw_market_data"

# \help start
def safe_float(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None

# \help end

def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("E: Missing KEY or URL")
    
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# helper function
def trans_date_to_timestamp(datetime_str: datetime):
    try: 
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        timestamp_ms = int(dt.timestamp() * 1000)
    except:
        raise ValueError("E: Not correct time value, should be in format of \"%Y-%m-%d %H:%M:%S\"")
    
    return timestamp_ms

def get_data_interval(api: str, start_time, end_time, page_size, chunk_minutes=10, end_ms=None):
    """
    This function fetch data in db by specify the time interval. 
    To acquire legitimate time interval, usetrans_date_to_timestamp function to get the accurate timestamp. 
    
    Note: time should be no earlier than 2026.06.21 20:30:00 utc
    
    """
    db = get_supabase()
    LEGIT = trans_date_to_timestamp("2026-06-20 20:30:00") 
    allowed = {
        "depth": {
            "limit": 1000
        }, 
        "trades": {
            "limit": 5000
        }, 
        "open_interests": {
            "limit": None
        }, 
        "klines": {
            "limit": 50, 
            "interval": 60
        }, 
        "indexes": {
            "limit": None
        }, 
        "funding_rates": {
            "limit": 10
        }
    }
    
    if api not in allowed.keys():
        raise ValueError("E: Requested api not in allowed list, should only request the following api node: [\"depth\", \"trades\", \"open_interests\", \"klines\", \"indexes\", \"funding_rates\"]")
    
    start_ms = trans_date_to_timestamp(start_time)
    end_ms = trans_date_to_timestamp(end_time)

    if end_ms < start_ms:
        raise ValueError("E: Try switch the start time and end time value")
    
    if start_ms < LEGIT or end_ms < LEGIT:
        raise ValueError("E: No data earlier than you requested, try fetch data later than 2026-06-20 20:30:00")
    
    run_chunk = chunk_minutes * 60 * 1000
    all_rows = []

    current_chunk_start = start_ms
    while current_chunk_start < end_ms:
        current_chunk_end = min(current_chunk_start + run_chunk, end_ms)
        offset = 0
        while True:
            resp = (
                db.table(RAW_TABLE)
                .select("*")
                .eq("api_name", api)
                .gte("local_response_time_ms", current_chunk_start)
                .lt("local_response_time_ms", current_chunk_end)
                .order("local_response_time_ms", desc=False)
                .range(offset, offset + page_size - 1)
                .execute()
            )

            rows = resp.data

            if not rows:
                break

            all_rows.extend(rows)

            if len(rows) < page_size:
                break

            offset += page_size

        current_chunk_start = current_chunk_end

    df = pd.DataFrame(all_rows)

    if not df.empty:
        df = df.sort_values("local_response_time_ms").reset_index(drop = True)
    
    return df


    db = get_supabase()
    
    
# research used function

def best_bid_ask(depth_data: pd.DataFrame):
    """
    return best bid and ask according to the given timestamp
    """
    rows = []
    for _, row in depth_data.items():
        bids_arr = row['bids']
        asks_arr = row['asks']
        updateTime = row['updateTime']

        best_bid, bid_amount = max(bids_arr, key=lambda x: safe_float(x[0]))

        best_ask, ask_amount = min(asks_arr, key=lambda x: safe_float(x[0]))

        best_bid = safe_float(best_bid)
        bid_amount = safe_float(bid_amount)
        best_ask = safe_float(best_ask)
        ask_amount = safe_float(ask_amount)

        mid = (best_ask + best_bid) / 2

        data = {
            "best_bids": best_bid, 
            "bid_amount": bid_amount,
            "best_asks": best_ask, 
            "ask_amount": ask_amount,
            "mid_price": mid, 
            "updateTime": updateTime
        }

        rows.append(data)
    
    return pd.DataFrame(data = rows)

def OFI(df):
    df = df.copy()
    df = df.sort_values("updateTime_dt").reset_index(drop=True)

    b_p_arr = df["best_bids"]
    b_v_arr = df["bid_amount"]
    a_p_arr = df["best_asks"]
    a_v_arr = df["ask_amount"]
    T = df["updateTime_dt"]

    pre_b_diff = b_p_arr.diff()
    pre_b_v = b_v_arr.shift(1)
    pre_a_diff = a_p_arr.diff()
    pre_a_v = a_v_arr.shift(1)

    e_arr = []
    for i in range(1, len(T)):
        e1 = safe_float(b_v_arr.iloc[i]) if pre_b_diff.iloc[i] >= 0 else 0
        e2 = safe_float(pre_b_v.iloc[i]) if pre_b_diff.iloc[i] <= 0 else 0

        e3 = safe_float(a_v_arr.iloc[i]) if pre_a_diff.iloc[i] <= 0 else 0
        e4 = safe_float(pre_a_v.iloc[i]) if pre_a_diff.iloc[i] >= 0 else 0

        ei = e1 - e2 - e3 + e4

        e_arr.append(ei)

    result = df.iloc[1:].copy().reset_index(drop=True)
    result["e_n"] = e_arr
    result["cum_OFI"] = result["e_n"].cumsum()

    return result

# this function is mostly generated by GPT with mile edit by author
def get_OFI_k(ofi_event_df, freq="1min", tick=0.1):
    """
    Aggregate event-level e_n into interval-level OFI_k.
    """

    df = ofi_event_df.copy()

    df = df.sort_values("updateTime_dt")
    df = df.set_index("updateTime_dt")

    ofi_k = (
        df
        .resample(freq, label="right", closed="right")
        .agg(
            OFI_k=("e_n", "sum"),
            n_events=("e_n", "count"),
            mid_price=("mid_price", "last"),
        )
        .reset_index()
        .rename(columns={"updateTime_dt": "t_k"})
    )

    ofi_k = ofi_k[ofi_k["n_events"] > 0].reset_index(drop=True)
    ofi_k["delta_mid_tick"] = ofi_k["mid_price"].diff() / tick
    ofi_k = ofi_k.dropna(subset=["delta_mid_tick"]).reset_index(drop=True)

    return ofi_k

def test_multiple_window(ofi_df):
    freqs = ["5s", "10s", "30s", "1min"]
    rows = []
    models = {}
    for freq in freqs:
        ofi_k = get_OFI_k(ofi_df, freq=freq, tick=0.1)
        regression_df = ofi_k[["OFI_k", "delta_mid_tick"]].dropna()
        y = regression_df["delta_mid_tick"]
        x = regression_df["OFI_k"]
        x = sm.add_constant(x)

        model = sm.OLS(y, x).fit()
        
        corr = regression_df["OFI_k"].corr(regression_df["delta_mid_tick"])

        rows.append({
            "freq": freq,
            "n_obs": len(regression_df),
            "corr": corr,
            "r_squared": model.rsquared,
            "beta": model.params["OFI_k"],
            "p_value": model.pvalues["OFI_k"],
        })

        models[freq] = model

    result = pd.DataFrame(rows)

    return result, models

def test_lagged_prediction(ofi_df, freq="5s", lag=1, tick=0.1):
    """
    We want to test whether OFI_k predicts future mid_price change.

    Regression Formula:
        delta_mid_tick_{k+lag} = alpha + beta * OFI_k + error
    """

    ofi_k = get_OFI_k(ofi_df, freq=freq, tick=tick).copy()
    target_col = f"future_delta_mid_tick_lag_{lag}"

    ofi_k[target_col] = ofi_k["delta_mid_tick"].shift(-lag)

    regression_df = ofi_k[["OFI_k", target_col]].dropna()

    y = regression_df[target_col]
    x = regression_df[["OFI_k"]]
    x = sm.add_constant(x)

    model = sm.OLS(y, x).fit()

    corr = regression_df["OFI_k"].corr(regression_df[target_col])

    print(f"\nLagged prediction test")
    print(f"freq = {freq}, lag = {lag}")
    print(f"corr(OFI_k, delta_mid_tick_k+{lag}) = {corr}")
    print(f"n = {len(regression_df)}")
    print(model.summary())

    return model, ofi_k

if __name__ == "__main__":
    # request time should be no earlier than utc time "2026-06-20 20:30:01" or "2026-06-20 20:30:02"
    start = "2026-06-21 20:10:00"
    end = "2026-06-23 20:10:00"
    
    depth_raw = get_data_interval(
        api = "depth",
        start_time=start,
        end_time=end,
        page_size =1000,
        chunk_minutes=10,
    )
    
    kline_raw = get_data_interval(
        api = "klines",
        start_time=start,
        end_time=end,
        page_size =1000,
        chunk_minutes=10,
    )

    
    # find best bid and ask 
    depth_data = depth_raw.data
    best_return = best_bid_ask(depth_data=depth_data)
    
    best_return["updateTime"] = pd.to_numeric(best_return["updateTime"])

    best_return["updateTime_dt"] = pd.to_datetime(
        best_return["updateTime"],
        unit="ms",
        utc=True
    )

    ofi_df = OFI(best_return)
   
    
    # OLS test model
    # 2 minutes with 5 second scale segment
    print("="*80)
    print("= SECTION 2 : EACH TIME SCALE CORRELATION")
    print("="*80)

    window_result, window_models = test_multiple_window(ofi_df)
    print("\nContemporaneous OFI test:")
    print(window_result)

    print("\n5s OLS summary:")
    print(window_models["5s"].summary())
    
    #Lagged test model
    print("="*80)
    print("= SECTION 3: TIME SCALE PREDICTIVITY")
    print("="*80)

    lag_model, lag_ofi_5s = test_lagged_prediction(
    ofi_df,
    freq="1min",
    lag=1,
    tick=0.1
)