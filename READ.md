# Market Dynamics Research Framework

A quantitative research framework for cryptocurrency perpetual futures that models **market microstructure**, **market structure**, and **market dynamics**.

Instead of directly predicting future prices, this project aims to understand **how order book events propagate through the market and ultimately drive price evolution**.

---

# Motivation

Most quantitative trading models are formulated as

```
P(t+1) = f(Xt)
```

where `Xt` denotes all observable market information.

Although such models often achieve strong predictive performance, they rarely explain **why prices move**.

This project instead asks a more fundamental question:

> **What is the mechanism that transforms order book events into market dynamics and eventually into price movements?**

Rather than treating markets as black-box prediction problems, this framework models financial markets as a dynamic system continuously driven by market microstructure.

---

# Research Philosophy

The proposed framework decomposes financial markets into three complementary layers:

```
Market Microstructure
          │
          ▼
Market Dynamics
          │
          ▼
Market Structure
          │
          ▼
 Price Evolution
```

Instead of learning prices directly, we first learn the hidden processes governing market behavior.

---

# Project Architecture

```
                 Pionex Public API
                        │
                        ▼
               Raw Market Data
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   Order Book        Trades         Klines
        │               │               │
        └───────────────┼───────────────┘
                        ▼
              Feature Engineering
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
 Market Structure                 Market Dynamics
        │                               │
        ▼                               ▼
 Structural HMM                  Dynamic HMM
        │                               │
        └───────────────┬───────────────┘
                        ▼
              Hidden Market States
                        │
                        ▼
              Market Force Analysis
```

---

# Data Collection

The framework continuously collects synchronized market data from the **Pionex Public API**.

Current datasets include:

* Order Book Depth
* Recent Trades
* Klines
* Book Ticker
* Mark Price
* Index Price
* Funding Rates
* Open Interest

All datasets are synchronized into a unified database for empirical research.

---

# Market Structure

Instead of analyzing every candle independently, the framework first extracts higher-level structural information.

Current structural features include:

* Swing High / Swing Low
* Pivot High / Pivot Low
* Pivot Return
* Pivot Direction
* Dominant Channel Slope

These features remove a large amount of local market noise while preserving long-term market geometry.

---

# Market Dynamics

Inspired by classical mechanics, market motion is represented using successive derivatives of price.

```
Position
    │
    ▼
Velocity
    │
    ▼
Acceleration
    │
    ▼
Jerk
```

Current motion features include:

## Position

Market price.

```
position = Close
```

---

## Velocity

First derivative of price.

```
velocity = Close.diff()
```

---

## Acceleration

First derivative of velocity.

```
acceleration = velocity.diff()
```

Acceleration measures how rapidly market momentum changes.

---

## Jerk

First derivative of acceleration.

```
jerk = acceleration.diff()
```

Jerk represents sudden changes in market acceleration and may provide early information before volatility expansion.

---

# Dual Hidden-State Representation

Instead of representing markets using a single hidden regime, this framework separates hidden states into two complementary components.

## Structural Regime

Describes the slowly evolving market geometry.

Current structural features:

* Pivot Return
* Pivot Direction
* Dominant Channel Slope

Structural regimes correspond to long-term market organization.

---

## Dynamic State

Describes short-term market motion.

Current dynamic features:

* Velocity
* Acceleration
* Jerk

Dynamic states capture instantaneous changes in market momentum.

---

Together,

```
Market State
=
(Structural Regime,
 Dynamic State)
```

providing a richer representation than conventional single-regime models.

---

# Hidden Market State Discovery

Both structural and dynamic states are learned using Hidden Markov Models (HMM).

The framework currently discovers:

* Bullish Structure
* Bearish Structure
* Neutral Structure

and

* Upward Dynamic State
* Downward Dynamic State
* Neutral Dynamic State

Extensive experiments using different random initializations show that the learned hidden-state feature means remain highly stable, indicating that the discovered regimes originate from the feature space rather than random initialization.

---

# Hidden Markov Model Considerations

Hidden Markov Models are employed as an unsupervised method for discovering latent market states.

However, several important considerations should be noted.

## Sensitivity to Initialization

Gaussian HMM is optimized using the Expectation-Maximization (EM) algorithm.

Different random initializations may converge to different local optima.

To evaluate robustness, we performed extensive experiments using hundreds of different random seeds.

The learned state means remained remarkably stable across random initializations, suggesting that the discovered market states originate from the feature space rather than random initialization.



## Choice of Number of States

This framework currently assumes three latent states.

- Bullish
- Bearish
- Neutral

However, financial markets are highly non-stationary.

During prolonged bear markets, forcing three states often results in

- Strong Bear
- Weak Bear
- Neutral

instead of

- Bull
- Bear
- Sideways.

Therefore, the semantic interpretation of each hidden state depends on the observation window.

Future work will investigate adaptive state numbers and multi-scale regime discovery.


## Window Dependency

Hidden regimes depend strongly on the selected training interval.

Different market cycles produce different latent structures.

Rather than assuming a universal regime, this framework studies

- local regimes
- multi-scale regimes
- adaptive regimes

across different market environments.

To illustrate, we choose a 1-day interval of **2025-12-23 ~ 2026-06-23** of BTC-USD, and we get the result of the HMM
| State  | return_to_previous_pivot | pivot_direction | structure_state |
| -------| -----------------------: | --------------: | --------------: |
| 0      |      -9.841982           |     -0.083333   |   -1929.545580  |
| 1      |       1.586896           |     0.031579    |   166.375937    |
| 2      |       -0.152460          |     0.0         |   -26.618025    |

Though exhibits a rather stable result, same on 1000 random seed test, the result is not satisfying.
Shown in the figure
![Structure](figure\fail_on_hmm_window.png)
This figure shows that the HMM model though work well on capturing the market downward movemnt, it did not do well on capturing the upward-movement

On the other hand, if we choose an interval that endows with **up and down** movement in the market, the result is satisfying,
Also, to demonstrate, a 1-day interval 

The Mean Matrix,

|structure_state | return_to_previous_pivot | pivot_direction | dominant_channel_slope |
|----------------| ------------------------:| ---------------:| ----------------------:|                                         
|    0.0         |          -6.486127       |    -0.153846    |      -1720.696085      |
|    1.0         |           8.702933       |     0.272727    |       964.173329       |
|    2.0         |           -0.099018      |     0.000000    |       66.205147        |

The classification is shown in figure:
![Structure](figure\success_on_hmm_window.png)                       


## Robustness Analysis

The proposed framework was evaluated using over one thousand different random initializations.

For both

- Structural HMM
- Dynamic HMM

the estimated state means remained highly consistent.

This suggests that the proposed feature engineering produces naturally separable latent structures, reducing the dependence on EM initialization.

---

# Market Force Hypothesis

Traditional quantitative models attempt to predict prices directly.

Instead, this framework hypothesizes that market microstructure generates **market forces**, which subsequently drive market dynamics.

```
Order Book
      │
      ▼
 Market Force
      │
      ▼
Dynamic State
      │
      ▼
Structural Regime
      │
      ▼
 Price
```

Potential force variables include:

* Order Flow Imbalance (OFI)
* Order Book Imbalance
* Hump Overlap
* Liquidity Profile
* Spread
* Open Interest
* Market Order Flow

The objective is to estimate how these forces influence hidden market dynamics.

---

# Empirical Findings

## Order Flow Imbalance

Using synchronized order book and trade data, we investigated the contemporaneous relationship between Order Flow Imbalance (OFI) and mid-price changes.

| Frequency  | Correlation |        R² |
| ---------- | ----------: | --------: |
| 5 seconds  |       0.751 |     0.564 |
| 10 seconds |       0.811 |     0.658 |
| 30 seconds |       0.821 |     0.674 |
| 1 minute   |   **0.897** | **0.805** |

At the one-minute timescale, OFI explains more than **80%** of contemporaneous mid-price variation.

---

# Research Roadmap

Current work:

* Hidden Structural Regime Discovery
* Hidden Dynamic State Discovery
* Dominant Channel Extraction
* Motion Hierarchy
* Robust HMM Initialization
* Order Flow Imbalance Analysis

Upcoming work:

* Hump Overlap
* Order Book Force Estimation
* Market Force Modeling
* Multi-scale Regime Detection
* Event-driven Price Impact
* Hidden State Transition Modeling

---

# Long-Term Vision

The ultimate objective is **not merely to forecast future prices**.

Instead, this project seeks to derive a physically interpretable equation describing financial markets.

```
Market Microstructure
        ↓
   Market Forces
        ↓
 Dynamic States
        ↓
Structural Regimes
        ↓
   Price Evolution
```

Rather than treating markets as black-box prediction systems, this framework aims to establish a mathematical theory explaining how liquidity, order flow, and market structure jointly determine price evolution.

---

# License

This repository is intended for academic research and educational purposes.
