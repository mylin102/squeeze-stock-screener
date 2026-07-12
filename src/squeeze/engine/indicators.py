import os

# Work around pandas_ta/numba cache issues observed in local Python 3.13 setups.
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

import pandas as pd
import numpy as np
import pandas_ta as ta

TAIEX_TICKER = "^TWII"


def add_rs_indicators(df: pd.DataFrame, benchmark_close: pd.Series) -> pd.DataFrame:
    """
    Add Relative Strength (RS) indicators to a ticker's DataFrame.

    Two series are produced:
      - RS_Ratio = Close / Benchmark_Close  (raw ratio, stable across download periods)
      - RS_Index = 100 * RS_Ratio / RS_Ratio.iloc[0]  (base-100 for charting)

    All feature computations (EMA, slope, new-high) use RS_Ratio internally so
    they are invariant to the download period's base date.

    Features (all prefixed 'RS_'):
      - RS_Ratio: raw Close/Benchmark ratio
      - RS_Index: base-100 index (for charting / visual comparison)
      - RS_EMA20 / RS_EMA60: smoothed RS_Ratio
      - RS_Slope_1d: 1-day pct_change of RS_EMA20 (%)
      - RS_Slope_5d: 5-day pct_change of RS_EMA20 (%)  — primary momentum
      - RS_Slope_20d: 20-day pct_change of RS_EMA20 (%) — trend momentum
      - RS_Above_EMA20 / RS_Above_EMA60: boolean
      - RS_EMA20_Above_EMA60: boolean
      - RS_New_High_60 / RS_New_High_120: event (excludes current bar)
      - RS_Percentile_60: 0-1 rank within 60 days
      - RS_Rising_10: RS_Ratio > value 10 bars ago

    Args:
        df: Ticker DataFrame with a 'Close' column and a DatetimeIndex.
        benchmark_close: Series of benchmark close prices, aligned by date.

    Returns:
        DataFrame with new RS_* columns added.
    """
    if df.empty or benchmark_close.empty:
        return df

    res = df.copy()

    # Align benchmark to ticker dates via forward-fill
    bm = benchmark_close.reindex(res.index, method="ffill")

    # 1. Raw ratio (stable across download periods)
    res["RS_Ratio"] = res["Close"] / bm

    # 2. Base-100 index (for charting)
    res["RS_Index"] = 100.0 * res["RS_Ratio"] / res["RS_Ratio"].iloc[0]
    res["RS_Base_Date"] = res.index[0]  # record base date for reproducibility

    # 3. Smoothed RS (using RS_Ratio so features are period-invariant)
    res["RS_EMA20"] = res["RS_Ratio"].ewm(span=20, adjust=False).mean()
    res["RS_EMA60"] = res["RS_Ratio"].ewm(span=60, adjust=False).mean()

    # 4. RS Slope (multi-day pct_change for stability)
    res["RS_Slope_1d"] = res["RS_EMA20"].pct_change(1) * 100.0
    res["RS_Slope_5d"] = res["RS_EMA20"].pct_change(5) * 100.0
    res["RS_Slope_20d"] = res["RS_EMA20"].pct_change(20) * 100.0
    # Mirror 1d slope as RS_Slope for backward compat
    res["RS_Slope"] = res["RS_Slope_1d"]

    # 5. Position vs EMAs
    res["RS_Above_EMA20"] = (res["RS_Ratio"] > res["RS_EMA20"]).fillna(False)
    res["RS_Above_EMA60"] = (res["RS_Ratio"] > res["RS_EMA60"]).fillna(False)
    res["RS_EMA20_Above_EMA60"] = (res["RS_EMA20"] > res["RS_EMA60"]).fillna(False)

    # 6. RS New Highs (exclude current bar — compare against prior rolling max)
    res["RS_New_High_60"] = (res["RS_Ratio"] > res["RS_Ratio"].shift(1).rolling(60, min_periods=20).max()).fillna(False)
    res["RS_New_High_120"] = (res["RS_Ratio"] > res["RS_Ratio"].shift(1).rolling(120, min_periods=40).max()).fillna(False)

    # 7. RS percentile within 60 days (0-1, for cross-stock ranking)
    rs_min_60 = res["RS_Ratio"].rolling(60, min_periods=20).min()
    rs_max_60 = res["RS_Ratio"].rolling(60, min_periods=20).max()
    res["RS_Percentile_60"] = ((res["RS_Ratio"] - rs_min_60) / (rs_max_60 - rs_min_60)).fillna(0.5).clip(0, 1)

    # 8. RS rising over 10 bars
    res["RS_Rising_10"] = (res["RS_Ratio"] > res["RS_Ratio"].shift(10)).fillna(False)

    return res


def calculate_squeeze_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate PowerSqueeze indicators and explicit Buy/Sell signals.
    
    Args:
        df: DataFrame with OHLCV data.
        
    Returns:
        pd.DataFrame: Original DataFrame with added squeeze indicators and signals.
    """
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    # 1. Standard TTM Squeeze using pandas-ta
    sqz = df.ta.squeeze(bb_length=20, bb_std=2.0, kc_length=20, kc_scalar=1.5, lazy=True)
    
    sqz_on_col = [c for c in sqz.columns if 'SQZ_ON' in c][0]
    mom_col = [c for c in sqz.columns if c.startswith('SQZ_') and c not in ['SQZ_ON', 'SQZ_OFF', 'SQZ_NO']][0]
    
    # 2. Custom Energy Level Calculation
    bb = df.ta.bbands(length=20, std=2.0)
    kc = df.ta.kc(length=20, scalar=1.5)
    
    bb_upper = bb.filter(like='BBU').iloc[:, 0]
    bb_lower = bb.filter(like='BBL').iloc[:, 0]
    kc_upper = kc.filter(like='KCU').iloc[:, 0]
    kc_lower = kc.filter(like='KCL').iloc[:, 0]
    
    bb_width = bb_upper - bb_lower
    kc_width = kc_upper - kc_lower
    
    squeeze_ratio = (kc_width - bb_width) / kc_width
    squeeze_ratio = squeeze_ratio.clip(lower=0, upper=1)
    
    energy_level = pd.cut(
        squeeze_ratio, 
        bins=[-np.inf, 0.3, 0.5, 0.7, np.inf], 
        labels=[0, 1, 2, 3]
    ).fillna(0).astype(int)
    
    # 3. Assemble Results
    result = df.copy()
    result['Squeeze_On'] = sqz[sqz_on_col].astype(bool)
    result['Energy_Level'] = energy_level
    result['Momentum'] = sqz[mom_col].fillna(0)
    
    # Fired: Not squeezed now but was squeezed in the previous bar
    result['Fired'] = (~result['Squeeze_On']) & (result['Squeeze_On'].shift(1) == True)
    result['Fired'] = result['Fired'].fillna(False)

    # 4. Explicit Signal Logic
    # Signals: Strong Buy, Buy, Sell, Wait
    def determine_signal(row):
        mom = row['Momentum']
        prev_mom = row['Prev_Momentum']
        fired = row['Fired']
        sqz_on = row['Squeeze_On']
        
        if fired and mom > 0:
            return "強烈買入 (爆發)"
        if fired and mom < 0:
            return "強烈賣出 (跌破)"
        
        if mom > 0:
            if mom > prev_mom:
                return "買入 (動能增強)"
            else:
                return "觀望 (動能減弱)"
        else: # mom <= 0
            if mom > prev_mom:
                return "觀察 (跌勢收斂)"
            else:
                return "賣出 (動能轉弱)"

    result['Prev_Momentum'] = result['Momentum'].shift(1).fillna(0)
    result['Signal'] = result.apply(determine_signal, axis=1)
    
    # 5. Trend Context (MA20)
    # Add comments to the file for all subsequent modifications as per user preference in ~/.gemini/GEMINI.md
    result["MA20"] = result["Close"].rolling(20).mean()
    result["MA20_Slope"] = result["MA20"].diff()
    result["MA20_Prev_Slope"] = result["MA20_Slope"].shift(1)
    result["MA20_Converging"] = (
        (result["MA20_Slope"] < 0) & 
        (result["MA20_Slope"] > result["MA20_Prev_Slope"])
    ).fillna(False)
    result["Close_Above_MA20"] = (result["Close"] > result["MA20"]).fillna(False)
    
    return result
