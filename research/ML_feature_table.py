# /research/ML_feature_table.py
import pandas as pd

feature_df = pd.read_pickle("data/features/feature_1m_180min.pkl")

df = feature_df[feature_df["fine_coverage"]].copy()
print(df.shape)
print(df[[
    "return_1m",
    "next_return_1m",
    "trade_imbalance",
    "book_imbalance",
    "depth_pressure",
    "buy_fuel",
    "sell_fuel",
    "net_fuel",
]].corr()["next_return_1m"].sort_values())
