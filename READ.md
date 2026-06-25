# Pionex Futures Market Data Collector

A Python-based utility to fetch crypto perpetual futures market data from the Pionex public API and perform order flow imbalance (OFI) research.

## Purpose
- Pull crypto perpetual futures market data from Pionex public API (**no API key required**).
- Collects and aggregates:
  1. Order book depth
  2. Recent taker-side trades
  3. Klines
  4. Book ticker
  5. Mark/index price and next funding rate
  6. Historical funding rates
  7. Open interest
  8. Simple imbalance features (e.g., Order Flow Imbalance, OFI)

---

## Research Findings (Updated: 2026-06-24)

Based on the collected data, we conducted an empirical analysis on the relationship between **Order Flow Imbalance (OFI)** and **Mid-Price Changes ($\Delta \text{mid\_tick}$)** across multiple timescales.

### 1. Contemporaneous OFI Analysis
We tested the simultaneous impact of OFI on price movements. The results show a **strong positive correlation** across all timescales, with explanatory power ($R^2$) increasing as the time window widens.

| Frequency | No. Observations | Correlation ($r$) | $R^2$ | Beta ($\beta$) | p-value |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **5s** | 359 | 0.7508 | 0.5638 | 2.1799 | $2.74 \times 10^{-66}$ |
| **10s** | 179 | 0.8114 | 0.6583 | 2.2506 | $3.91 \times 10^{-43}$ |
| **30s** | 59 | 0.8210 | 0.6741 | 2.2911 | $1.69 \times 10^{-15}$ |
| **1min** | 29 | 0.8970 | 0.8046 | 2.4673 | $4.51 \times 10^{-11}$ |

> **Key Takeaway:** At the 1-minute scale, contemporaneous OFI explains over **80%** of the mid-price variance ($R^2 = 0.8046$).

#### 5s OLS Regression Snapshot
```text
Dep. Variable: delta_mid_tick         R-squared: 0.564
Method:        Least Squares          Adj. R-squared: 0.563
F-statistic:   461.4                  Prob (F-statistic): 2.74e-66
------------------------------------------------------------------------------
               coef    std err          t      P>|t|      [0.025      0.975]
------------------------------------------------------------------------------
const          0.4487      1.791      0.251      0.802      -3.074       3.971
OFI_k          2.1799      0.101     21.480      0.000       1.980       2.379