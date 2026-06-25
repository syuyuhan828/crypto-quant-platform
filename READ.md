"""
Pionex Futures Market Data Collector

Purpose:
- Pull crypto perpetual futures market data from Pionex public API.
- No API key required for these public market endpoints.
- Collects:
  1. Order book depth
  2. Recent taker-side trades
  3. Klines
  4. Book ticker
  5. Mark/index price and next funding rate
  6. Historical funding rates
  7. Open interest
  8. Simple imbalance features

Install:
    pip install requests pandas

Run:
    python pionex_market_data.py
"""


Current status on research:
we have a redo on 20206-06-24\
The result is as followed:
================================================================================
= SECTION 2 : EACH TIME SCALE CORRELATION
================================================================================

Contemporaneous OFI test:
   freq  n_obs      corr  r_squared      beta       p_value
0    5s    359  0.750849   0.563775  2.179869  2.736710e-66
1   10s    179  0.811367   0.658317  2.250563  3.913559e-43
2   30s     59  0.821013   0.674062  2.291131  1.692844e-15
3  1min     29  0.896987   0.804586  2.467284  4.506070e-11

5s OLS summary:
                            OLS Regression Results                            
==============================================================================
Dep. Variable:         delta_mid_tick   R-squared:                       0.564
Model:                            OLS   Adj. R-squared:                  0.563
Method:                 Least Squares   F-statistic:                     461.4
Date:                  週三, 24 六月 2026   Prob (F-statistic):           2.74e-66
Time:                        20:17:54   Log-Likelihood:                -1769.1
No. Observations:                 359   AIC:                             3542.
Df Residuals:                     357   BIC:                             3550.
Df Model:                           1                                         
Covariance Type:            nonrobust                                         
==============================================================================
                 coef    std err          t      P>|t|      [0.025      0.975]
------------------------------------------------------------------------------
const          0.4487      1.791      0.251      0.802      -3.074       3.971
OFI_k          2.1799      0.101     21.480      0.000       1.980       2.379
==============================================================================
Omnibus:                       40.424   Durbin-Watson:                   2.231
Prob(Omnibus):                  0.000   Jarque-Bera (JB):              240.534
Skew:                           0.125   Prob(JB):                     5.87e-53
Kurtosis:                       7.002   Cond. No.                         17.9
==============================================================================

Notes:
[1] Standard Errors assume that the covariance matrix of the errors is correctly specified.
================================================================================
= SECTION 3: TIME SCALE PREDICTIVITY
================================================================================

Lagged prediction test
freq = 1min, lag = 1
corr(OFI_k, delta_mid_tick_k+1) = -0.004954560371299704
n = 28
                                 OLS Regression Results                                
=======================================================================================
Dep. Variable:     future_delta_mid_tick_lag_1   R-squared:                       0.000
Model:                                     OLS   Adj. R-squared:                 -0.038
Method:                          Least Squares   F-statistic:                 0.0006383
Date:                           週三, 24 六月 2026   Prob (F-statistic):              0.980
Time:                                 20:17:54   Log-Likelihood:                -186.36
No. Observations:                           28   AIC:                             376.7
Df Residuals:                               26   BIC:                             379.4
Df Model:                                    1                                         
Covariance Type:                     nonrobust                                         
==============================================================================
                 coef    std err          t      P>|t|      [0.025      0.975]
------------------------------------------------------------------------------
const        -54.5091     40.163     -1.357      0.186    -137.065      28.047
OFI_k         -0.0141      0.559     -0.025      0.980      -1.163       1.135
==============================================================================
Omnibus:                        0.887   Durbin-Watson:                   1.981
Prob(Omnibus):                  0.642   Jarque-Bera (JB):                0.291
Skew:                          -0.237   Prob(JB):                        0.865
Kurtosis:                       3.155   Cond. No.                         78.3
==============================================================================

Notes:
[1] Standard Errors assume that the covariance matrix of the errors is correctly specified.