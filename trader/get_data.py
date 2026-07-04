import os
import pandas as pd
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from matplotlib import colors as mcolors
from datetime import datetime, timezone
import yfinance as yf # experiment
import mplfinance as mpf # experiment
from pathlib import Path
from supabase import create_client
from dotenv import load_dotenv
import time
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler


load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_PROJ_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
RAW_TABLE = "pionex_raw_market_data"

#=========================helper
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

def safe_float(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None

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
    Note: time interval 2026.06.24 15:00:00 UTC - 2026.06.29 23:00:00 UTC has a data gap, due to supabase died down
    
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

def get_klines(start=None, end=None, is_experiment=True, ticker="BTC-USD", interval="15m", start_time=None, end_time=None):
    """
    fetch data from
    1. yfinance (if it is a experiment test)
    2. database (if this is script is running on a formal basis)

    Note: if it is not experimental, data will only return a data that is a second_scale.
    """
    df: pd.DataFrame = pd.DataFrame()

    if is_experiment:
        starter = time.time()
        data = yf.download(ticker, start, end, interval=interval)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        df = pd.DataFrame(data).reset_index()

        df = df.rename(columns={
            "Datetime": "datetime",
            "Date": "datetime"
        })

        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        

        df["local_response_time_ms"] = (
            df["datetime"].astype("int64") * 1000
        )

        df = df.set_index("datetime", drop=False)
        ender = time.time()

        print(f"for experimental data collection, {round(ender-starter, 2)}s are used to process.")

    else:
        starter = time.time()
        klines = get_data_interval(
            "klines",
            start_time=start_time,
            end_time=end_time,
            page_size=1000,
            chunk_minutes=10,
        )

        rows = []
        for _, row in klines.iterrows():
            for d in row["data"]["klines"]:
                rows.append(d)

        df = pd.DataFrame(rows)

        df = (
            df
            .drop_duplicates(subset=["time"], keep="last")
            .sort_values("time")
            .reset_index(drop=True)
        )
        df["local_response_time_ms"] = df["time"]
        if start_time is not None:
            start_time = trans_date_to_timestamp(start_time)
            df = df[df["local_response_time_ms"] >= start_time]

        if end_time is not None:
            end_time = trans_date_to_timestamp(end_time)
            df = df[df["local_response_time_ms"] <= end_time]
        df = df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        })

        df["datetime"] = pd.to_datetime(
            df["local_response_time_ms"],
            unit="ms",
            utc=True
        )

        df = df.set_index("datetime", drop=False)
        ender = time.time()

        print(f"for formal used data collection, {round(ender-starter)}s are used to process.")
        
    cols = [
        "datetime",
        "local_response_time_ms",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    df = df[cols]
    return df


if __name__ == "__main__":
    
    start = "2024-01-23"
    start_ms = "2026-06-21 20:30:00"
    end = "2024-06-23"
    end_ms = "2026-06-22 00:30:00"

    RANDOM_SEED = 42

    # 9s for 4Hr data
    df = get_klines(start_time=start_ms, end_time=end_ms, is_experiment=False)