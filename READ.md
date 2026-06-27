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


# Market Dynamics Hypothesis

## Motivation

Traditional quantitative trading models focus on predicting the next price movement directly,

\[
P_{t+1}=f(X_t)
\]

where \(X_t\) denotes all observable market information.

However, this approach ignores an important question:

> **What is the mechanism that causes prices to move?**

Instead of predicting the price itself, we hypothesize that financial markets behave as a dynamic system, where market microstructure continuously exerts "forces" on prices.

---

# Physics Analogy

Classical mechanics describes the evolution of an object as

\[
F=ma
\]

where

- Position
- Velocity
- Acceleration

describe different orders of motion.

We propose a similar hierarchy for financial markets.

---

# Level 0 — Position

The market price itself.

\[
P_t
\]

Python

```python
price = Close
```

---

# Level 1 — Velocity

The first derivative of price.

\[
v_t
=
\frac{P_t-P_{t-1}}{P_{t-1}}
\]

which corresponds to

```python
velocity = Close.pct_change()
```

This is the traditional financial return.

---

# Level 2 — Acceleration

The first derivative of return (second derivative of price).

\[
a_t
=
v_t-v_{t-1}
\]

or

```python
acceleration = velocity.diff()
```

Acceleration measures how rapidly market momentum changes.

Large acceleration often appears before explosive breakouts.

---

# Level 3 — Jerk

The derivative of acceleration.

\[
j_t
=
a_t-a_{t-1}
\]

```python
jerk = acceleration.diff()
```

This describes sudden changes of market acceleration.

Although rarely studied in finance, it may contain useful information before volatility expansion.

---

# Market Microstructure as Force

Instead of viewing order book information as direct predictors of price,

we interpret them as **market forces**.

Potential force variables include

- Order Flow Imbalance (OFI)
- Order Book Imbalance
- Hump Overlap
- Liquidity
- Spread
- Open Interest
- Market Order Flow

Collectively,

\[
F_t
=
f(\text{Order Book})
\]

---

# Proposed Market Dynamics

Rather than

\[
Price=f(X)
\]

we propose

\[
F_t
\rightarrow
a_t
\rightarrow
v_t
\rightarrow
P_t
\]

which can be interpreted as

```
Order Book
      │
      ▼
 Market Force
      │
      ▼
Acceleration
      │
      ▼
 Velocity
      │
      ▼
  Price
```

This hypothesis suggests that market microstructure influences acceleration first, acceleration changes velocity, and velocity ultimately determines price evolution.

---

# Pivot-Level Dynamics

To capture market structure, we define pivot-based features.

## Pivot Return

The percentage movement between two consecutive confirmed pivots.

Represents the velocity of a swing.

---

## Pivot Direction

\[
\{-1,0,+1\}
\]

where

- +1 = Upward Pivot
- -1 = Downward Pivot
- 0 = No Pivot

---

## Additional Local Dynamics

Bar-level quantities include

- Return
- Velocity
- Acceleration
- Jerk

These describe the local dynamics occurring between pivots.

---

# Hidden Market Regime

Instead of manually defining

- Uptrend
- Downtrend
- Sideways

we allow Hidden Markov Models (HMM) to discover latent market states.

Candidate features include

- Pivot Return
- Pivot Direction
- Velocity
- Acceleration
- Order Book Force

The learned hidden states are then interpreted as

- Upward Breakout
- Downward Breakout
- Sideways / Mundane

depending on their statistical characteristics.

---

# Long-Term Goal

The ultimate objective is **not merely to predict future prices**, but to derive a market equation of motion analogous to Newtonian mechanics.

Specifically,

\[
\boxed{
\frac{d^2P}{dt^2}
=
f(\text{Order Book Features})
}
\]

where

\[
f(\cdot)
\]

is learned from market microstructure.

If validated, this framework provides a physically interpretable description of how liquidity, order flow, and market structure jointly drive price evolution.