import pandas as pd
import mplfinance as mpf
import pandas_ta as ta
import numpy as np
import os

def plot_ticker(ticker_df: pd.DataFrame, ticker_symbol: str, output_path: str):
    """
    Generates a candlestick chart with technical indicators for a given ticker.
    
    Args:
        ticker_df: DataFrame containing OHLCV and Squeeze indicators.
        ticker_symbol: String representing the ticker symbol.
        output_path: Path where the PNG image will be saved.
    """
    # Ensure index is DatetimeIndex
    if not isinstance(ticker_df.index, pd.DatetimeIndex):
        ticker_df.index = pd.to_datetime(ticker_df.index)

    df = ticker_df.copy()
    
    # Bollinger Bands
    bb = df.ta.bbands(length=20, std=2.0)
    bb_upper = bb.filter(like='BBU').iloc[:, 0]
    bb_lower = bb.filter(like='BBL').iloc[:, 0]
    
    # Keltner Channels
    kc = df.ta.kc(length=20, scalar=1.5)
    kc_upper = kc.filter(like='KCU').iloc[:, 0]
    kc_lower = kc.filter(like='KCL').iloc[:, 0]
    
    # Ensure Squeeze indicators exist
    if 'Momentum' not in df.columns or 'Squeeze_On' not in df.columns:
        from squeeze.engine.indicators import calculate_squeeze_indicators
        df = calculate_squeeze_indicators(df)

    # --- OPTIMIZATION: Limit Plotting Range to 6 Months ---
    # We keep full data for indicators but only plot the last ~130 bars (6 months)
    plot_df = df.tail(130).copy()
    
    # Recalculate indicators for the plotting range if needed (or just slice them)
    bb_upper_p = bb_upper.tail(130)
    bb_lower_p = bb_lower.tail(130)
    kc_upper_p = kc_upper.tail(130)
    kc_lower_p = kc_lower.tail(130)

    plots = [
        # Bollinger Bands (dashed)
        mpf.make_addplot(bb_upper_p, color='blue', linestyle='dashed', alpha=0.3),
        mpf.make_addplot(bb_lower_p, color='blue', linestyle='dashed', alpha=0.3),
        # Keltner Channels (solid)
        mpf.make_addplot(kc_upper_p, color='orange', alpha=0.3),
        mpf.make_addplot(kc_lower_p, color='orange', alpha=0.3),
    ]
    
    # Squeeze Momentum Histogram colors
    mom = plot_df['Momentum']
    hist_colors = []
    for i in range(len(mom)):
        val = mom.iloc[i]
        prev_val = mom.iloc[i-1] if i > 0 else 0
        
        if val >= 0:
            if val >= prev_val:
                hist_colors.append('cyan') # Increasing bullish
            else:
                hist_colors.append('blue') # Decreasing bullish
        else:
            if val <= prev_val:
                hist_colors.append('red') # Increasing bearish
            else:
                hist_colors.append('maroon') # Decreasing bearish
                
    plots.append(mpf.make_addplot(plot_df['Momentum'], type='bar', panel=1, color=hist_colors, secondary_y=False))
    
    # --- OPTIMIZATION: Squeeze Dots (Energy Markers) ---
    squeeze_on = plot_df['Squeeze_On']
    energy = plot_df['Energy_Level']
    dot_colors = ['red' if val else 'lime' for val in squeeze_on]
    
    # Scaled sizes: Higher energy = Larger dots
    # Energy levels are 0-3. Map to sizes 10, 30, 60, 100
    dot_sizes = [10 + (e * 40) if s else 10 for s, e in zip(squeeze_on, energy)]
    
    # Plot dots at 0 on the momentum panel
    plots.append(mpf.make_addplot(np.zeros(len(plot_df)), type='scatter', markersize=dot_sizes, marker='o', 
                                  color=dot_colors, panel=1, secondary_y=False))

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Generate Plot using plot_df (6 months)
    mpf.plot(plot_df, type='candle', style='charles', addplot=plots, 
             title=f"{ticker_symbol} - Squeeze Analysis (6mo)", 
             savefig=output_path, volume=True, 
             panel_ratios=(4, 2), # Main plot and Indicators
             show_nontrading=False,
             tight_layout=True)
