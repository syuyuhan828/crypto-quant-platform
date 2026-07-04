import pandas as pd
import numpy as np
import mplfinance as mpf # experiment
from get_data import get_klines

def get_pivot(df: pd.DataFrame, show_plot: bool=False):

    df = df.copy()
    numeric_cols = ["Open", "High", "Low", "Close", "Volume"]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df['swing_high'] = np.where(
        df["High"] > df["High"].shift(1), "HH",
        np.where(
            df["High"] < df["High"].shift(1), "LH", None
        )
    )

    df['swing_high_continuous'] = np.where(
        df["swing_high"] != df['swing_high'].shift(-1),
        df['swing_high'],
        np.nan
    )
    
    df["hh_point"] = np.where(
        df["swing_high_continuous"] == "HH",
        df["High"], np.nan
    )

    df['swing_low'] = np.where(
        df["Low"] < df["Low"].shift(1), "LL",
        np.where(df["Low"] > df["Low"].shift(1), 'HL', None)
    )

    df['swing_low_continuous'] = np.where(
        df["swing_low"] != df["swing_low"].shift(-1),
        df["swing_low"], np.nan
    )

    df['ll_point'] = np.where(
        df["swing_low_continuous"] == "LL",
        df["Low"], np.nan
    )

    #check ll idx and its compensate
    ll_idx = df.index[df["swing_low_continuous"] =="LL"].tolist()
    df["ref_hh"] = np.nan

    
    for i in range(len(ll_idx)-1):
        start = ll_idx[i]
        end = ll_idx[i+1]
        segment = df.loc[start:end].iloc[1:-1]
        idx = segment["High"].idxmax()
        value = segment.loc[idx, "High"]

        df.loc[idx, "ref_hh"] = value

    len_ll = len(ll_idx)
    len_ref_hh = len(df['ref_hh'].dropna())

    on_len_ll = len_ll + len_ref_hh

    #check hh and its compensate
    hh_idx = df.index[df["swing_high_continuous"] == "HH"].tolist()
    df["ref_ll"] = np.nan

    for i in range(len(hh_idx) - 1):
        start = hh_idx[i]
        end = hh_idx[i + 1]

        segment = df.loc[start:end].iloc[1:-1]

        idx = segment["Low"].idxmin()
        value = segment.loc[idx, "Low"]

        df.loc[idx, "ref_ll"] = value

    len_hh = len(hh_idx)
    len_ref_ll = len(df['ref_ll'].dropna())
    on_len_hh = len_hh + len_ref_ll
    
    if on_len_hh >= on_len_ll:
        df['pivot_high'] = df['ref_hh']
        df['pivot_low'] = df['ll_point']
    else:
        df['pivot_high'] = df['hh_point']
        df['pivot_low'] = df['ref_ll']

    if show_plot:
        plot_df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        addplots = [
            mpf.make_addplot(df["pivot_high"], type="scatter", marker="v", markersize=80, color='green'),
            mpf.make_addplot(df["pivot_low"], type="scatter", marker="^", markersize=80, color='red'),
        ]
        mpf.plot(
            plot_df,
            type="candle",
            volume=False,
            addplot=addplots,
            figsize=(14, 8),
            style='yahoo',
        )

    return df[["Open", "High", "Low", "Close", "Volume", "pivot_high", "pivot_low"]]

if __name__ == "__main__":
    
    # small time scale: 1 minute scale
    start_ms = "2026-06-20 20:30:00"
    end_ms = "2026-06-23 20:30:00"

    # 9s for 4Hr data
    df = get_klines(start_time=start_ms, end_time=end_ms, is_experiment=False)

    pivot_df = get_pivot(df, show_plot=True)