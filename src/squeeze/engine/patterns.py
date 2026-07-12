import pandas as pd
import numpy as np
from squeeze.engine.indicators import calculate_squeeze_indicators, add_rs_indicators

# RS feature keys returned by all detection functions when benchmark is available
RS_RESULT_KEYS = [
    "rs_ratio", "rs_index", "rs_ema20", "rs_ema60",
    "rs_slope_1d", "rs_slope_5d", "rs_slope_20d",
    "rs_above_ema20", "rs_above_ema60", "rs_ema20_above_ema60",
    "rs_new_high_60", "rs_new_high_120", "rs_rising_10",
    "rs_percentile_60",
]


def _add_rs_to_result(result: dict, df: pd.DataFrame) -> dict:
    """Populate RS fields in a result dict from the last row of df if RS_Ratio exists."""
    if "RS_Ratio" not in df.columns:
        return result
    latest = df.iloc[-1]
    close = latest.get("Close", 0)
    # Price new high (same lookback: shift(1) to exclude current bar)
    price_new_high_60 = bool(
        close > df["Close"].shift(1).rolling(60, min_periods=20).max().iloc[-1]
    ) if "Close" in df.columns and len(df) >= 30 else False
    # RS new high (already computed as shift(1)-based in indicators)
    rs_new_high_60 = bool(latest.get("RS_New_High_60", False))
    # RS high while price is not — with guard: price must be within 10% of its 60d high
    price_60_max = float(df["Close"].rolling(60, min_periods=20).max().iloc[-1]) if "Close" in df.columns else 0.0
    price_dist_to_high = (float(close) / price_60_max - 1.0) if price_60_max > 0 else 0.0
    rs_high_price_not_high = (
        rs_new_high_60
        and not price_new_high_60
        and price_dist_to_high >= -0.10
    )

    result.update({
        "rs_ratio": float(latest.get("RS_Ratio", np.nan)),
        "rs_index": float(latest.get("RS_Index", np.nan)),
        "rs_ema20": float(latest.get("RS_EMA20", np.nan)),
        "rs_ema60": float(latest.get("RS_EMA60", np.nan)),
        "rs_slope_1d": float(latest.get("RS_Slope_1d", np.nan)),
        "rs_slope_5d": float(latest.get("RS_Slope_5d", np.nan)),
        "rs_slope_20d": float(latest.get("RS_Slope_20d", np.nan)),
        # Mirror 1d as rs_slope for backward compat
        "rs_slope": float(latest.get("RS_Slope", np.nan)),
        "rs_above_ema20": bool(latest.get("RS_Above_EMA20", False)),
        "rs_above_ema60": bool(latest.get("RS_Above_EMA60", False)),
        "rs_ema20_above_ema60": bool(latest.get("RS_EMA20_Above_EMA60", False)),
        "rs_new_high_60": rs_new_high_60,
        "rs_new_high_120": bool(latest.get("RS_New_High_120", False)),
        "rs_rising_10": bool(latest.get("RS_Rising_10", False)),
        "rs_percentile_60": float(latest.get("RS_Percentile_60", 0.5)),
        "rs_high_price_not_high": rs_high_price_not_high,
        "price_dist_to_high_60": price_dist_to_high,
    })
    return result


def _build_rs_signal(result: dict) -> str:
    """Derive a qualitative RS signal (for data logging only, not used in scoring)."""
    score = 0
    reasons = []
    if result.get("rs_above_ema20"):
        score += 1
        reasons.append("RS>EMA20")
    if result.get("rs_above_ema60"):
        score += 1
        reasons.append("RS>EMA60")
    if result.get("rs_slope_5d", 0) > 0:  # use 5d slope for stability
        score += 1
        reasons.append("Slope5d↑")
    if result.get("rs_new_high_60"):
        score += 2
        reasons.append("RS_60H")
    if result.get("rs_new_high_120"):
        score += 2
        reasons.append("RS_120H")
    if result.get("rs_rising_10"):
        score += 1
        reasons.append("RS_Rise10")
    if result.get("rs_high_price_not_high"):
        score += 2
        reasons.append("RS_High_Price_Not")
    if result.get("rs_slope_5d", 0) > 0 and result.get("rs_above_ema20") and result.get("rs_above_ema60"):
        score += 1
        reasons.append("RS_Accel")
    if score >= 6:
        signal = "強勢 (RS強勁)"
    elif score >= 3:
        signal = "偏強 (RS上升)"
    elif score <= -2:
        signal = "偏弱 (RS下降)"
    else:
        signal = "中性"
    return signal


def detect_squeeze(df: pd.DataFrame, benchmark_close: pd.Series | None = None) -> dict:
    """
    Detect the Squeeze status for a given stock based on its historical data.
    
    Args:
        df: DataFrame with OHLCV data.
        
    Returns:
        dict: A dictionary containing the latest squeeze status:
            - 'is_squeezed' (bool): True if currently in a squeeze.
            - 'energy_level' (int): A value from 0-3 indicating squeeze compression.
            - 'momentum' (float): A normalized momentum value.
            - 'fired' (bool): True if the squeeze just fired.
            - 'timestamp' (str): The date of the analysis.
    """
    if df.empty or len(df) < 30: # Need enough data for indicators
        return {
            'is_squeezed': False,
            'energy_level': 0,
            'momentum': 0.0,
            'fired': False,
            'timestamp': None
        }
        
    # Calculate indicators
    df_with_indicators = calculate_squeeze_indicators(df)
    
    # Add RS indicators if benchmark data is available
    if benchmark_close is not None and not benchmark_close.empty:
        df_with_indicators = add_rs_indicators(df_with_indicators, benchmark_close)

    # Get the latest bar
    latest_bar = df_with_indicators.iloc[-1]

    # Volume expansion ratio (current volume / 20-day avg volume)
    vol_series = df_with_indicators["Volume"]
    vol_avg_20 = vol_series.rolling(20).mean().iloc[-1] if len(vol_series) >= 20 else vol_series.mean()
    volume_expansion_ratio = float(vol_series.iloc[-1] / vol_avg_20) if vol_avg_20 > 0 else 1.0

    result = {
        'is_squeezed': bool(latest_bar['Squeeze_On']),
        'energy_level': int(latest_bar['Energy_Level']),
        'momentum': float(latest_bar['Momentum']),
        'prev_momentum': float(latest_bar['Prev_Momentum']),
        'squeeze_on': bool(latest_bar['Squeeze_On']),
        'fired': bool(latest_bar['Fired']),
        'Signal': str(latest_bar.get('Signal', '觀望')),
        'Close': float(latest_bar['Close']),
        'timestamp': str(latest_bar.name),
        'ma20': float(latest_bar['MA20']),
        'ma20_slope': float(latest_bar['MA20_Slope']),
        'ma20_converging': bool(latest_bar['MA20_Converging']),
        'close_above_ma20': bool(latest_bar['Close_Above_MA20']),
        'volume_expansion_ratio': volume_expansion_ratio,
        'volume_expansion': volume_expansion_ratio >= 1.5,
    }
    # Attach RS fields
    result = _add_rs_to_result(result, df_with_indicators)
    if benchmark_close is not None:
        result["rs_signal"] = _build_rs_signal(result)
    return result

def detect_houyi_shooting_sun(df: pd.DataFrame, benchmark_close: pd.Series | None = None) -> dict:
    """
    Detect the 'Houyi Shooting the Sun' pattern.
    
    Criteria:
    1. Rally: >20% gain in a 30-day window within the last 60 days.
    2. Retracement: Current price within 0.5 - 0.7 Fibonacci retracement of that rally.
    3. Squeeze: TTM Squeeze is ON.
    4. Shooting Star: Upper wick >= 2x real body in the last 5 bars.
    
    Args:
        df: DataFrame with OHLCV data.
        
    Returns:
        dict: Pattern detection results and metadata.
    """
    if df.empty or len(df) < 60:
        return {
            'is_houyi': False,
            'rally_pct': 0.0,
            'fib_level': 0.0,
            'squeeze_on': False,
            'shooting_star': False
        }

    # 1. Calculate Indicators
    df_indicators = calculate_squeeze_indicators(df)
    
    # Add RS indicators if benchmark data is available
    if benchmark_close is not None and not benchmark_close.empty:
        df_indicators = add_rs_indicators(df_indicators, benchmark_close)
    
    latest_bar = df_indicators.iloc[-1]
    
    # 2. Rally & Fib Detection
    # Look back 60 bars to find the highest high
    lookback = 60
    window = df.iloc[-lookback:]
    peak_idx = window['High'].idxmax()
    peak_price = window['High'].max()
    
    # Find the lowest low in the 30 days preceding that peak
    peak_pos = df.index.get_loc(peak_idx)
    start_pos = max(0, peak_pos - 30)
    preceding_window = df.iloc[start_pos:peak_pos + 1]
    trough_price = preceding_window['Low'].min()
    
    rally_pct = (peak_price - trough_price) / trough_price if trough_price > 0 else 0
    
    # Current price vs Fib levels
    current_price = latest_bar['Close']
    if peak_price > trough_price:
        fib_level = (peak_price - current_price) / (peak_price - trough_price)
    else:
        fib_level = 0.0
        
    # 3. Squeeze Check
    squeeze_on = bool(latest_bar['Squeeze_On'])
    
    # 4. Shooting Star Check (most recent 5 bars)
    shooting_star = False
    recent_bars = df.iloc[-5:]
    for _, bar in recent_bars.iterrows():
        body = abs(bar['Close'] - bar['Open'])
        upper_wick = bar['High'] - max(bar['Close'], bar['Open'])
        if body < 0.001: # Avoid division by zero for Doji-like stars
            if upper_wick > 0:
                shooting_star = True
                break
        elif (upper_wick / body) >= 2.0:
            shooting_star = True
            break
            
    is_houyi = bool(
        rally_pct >= 0.2 and
        0.4 <= fib_level <= 0.75 and # Range encompassing 0.5-0.618 with some buffer
        squeeze_on and
        shooting_star
    )
    
    result = {
        'is_houyi': is_houyi,
        'rally_pct': float(rally_pct),
        'fib_level': float(fib_level),
        'squeeze_on': squeeze_on,
        'energy_level': int(latest_bar['Energy_Level']),
        'momentum': float(latest_bar['Momentum']),
        'prev_momentum': float(latest_bar['Prev_Momentum']),
        'fired': bool(latest_bar['Fired']),
        'shooting_star': shooting_star,
        'Close': float(latest_bar['Close']),
        'Signal': str(latest_bar.get('Signal', '觀望')),
    }
    result = _add_rs_to_result(result, df_indicators)
    if benchmark_close is not None:
        result["rs_signal"] = _build_rs_signal(result)
    return result

def detect_whale_trading(df_daily: pd.DataFrame, benchmark_close: pd.Series | None = None) -> dict:
    """
    Detect the 'Whale Trading' multi-timeframe alignment pattern.
    
    Criteria:
    1. Daily Squeeze ON.
    2. Weekly Squeeze ON.
    3. Momentum not deeply negative on both (>-0.5).
    
    Args:
        df_daily: DataFrame with Daily OHLCV data.
        
    Returns:
        dict: Pattern detection results and metadata.
    """
    if df_daily.empty or len(df_daily) < 100:
        return {
            'is_whale': False,
            'daily_squeeze': False,
            'weekly_squeeze': False,
            'daily_momentum': 0.0,
            'weekly_momentum': 0.0
        }

    # 1. Daily indicators
    df_daily_res = calculate_squeeze_indicators(df_daily)
    
    # Add RS indicators if benchmark data is available
    if benchmark_close is not None and not benchmark_close.empty:
        df_daily_res = add_rs_indicators(df_daily_res, benchmark_close)
    
    latest_daily = df_daily_res.iloc[-1]
    
    # 2. Resample to Weekly
    # Ensure index is datetime for resampling
    if not isinstance(df_daily.index, pd.DatetimeIndex):
        df_daily.index = pd.to_datetime(df_daily.index)
        
    logic = {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}
    df_weekly = df_daily.resample('W').apply(logic).dropna()
    
    if len(df_weekly) < 30:
        return {
            'is_whale': False,
            'daily_squeeze': bool(latest_daily['Squeeze_On']),
            'weekly_squeeze': False,
            'daily_momentum': float(latest_daily['Momentum']),
            'weekly_momentum': 0.0
        }
        
    # 3. Weekly indicators
    df_weekly_res = calculate_squeeze_indicators(df_weekly)
    latest_weekly = df_weekly_res.iloc[-1]
    
    # 4. Alignment
    daily_sq = bool(latest_daily['Squeeze_On'])
    weekly_sq = bool(latest_weekly['Squeeze_On'])
    daily_mom = float(latest_daily['Momentum'])
    weekly_mom = float(latest_weekly['Momentum'])
    
    # Signal if both are squeezed and momentum is positive
    is_whale = daily_sq and weekly_sq and daily_mom > 0 and weekly_mom > 0
    
    result = {
        'is_whale': bool(is_whale),
        'daily_squeeze': daily_sq,
        'weekly_squeeze': weekly_sq,
        'squeeze_on': daily_sq,
        'daily_momentum': daily_mom,
        'weekly_momentum': weekly_mom,
        'momentum': daily_mom,
        'prev_momentum': float(df_daily_res.iloc[-1]['Prev_Momentum']),
        'energy_level': int(latest_daily['Energy_Level']),
        'fired': bool(latest_daily['Fired']),
        'Close': float(latest_daily['Close']),
        'Signal': str(latest_daily.get('Signal', '觀望')),
    }
    result = _add_rs_to_result(result, df_daily_res)
    if benchmark_close is not None:
        result["rs_signal"] = _build_rs_signal(result)
    return result
