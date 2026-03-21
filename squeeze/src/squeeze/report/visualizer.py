import pandas as pd
import mplfinance as mpf
import pandas_ta as ta
import numpy as np
import os

def plot_ticker(ticker_df: pd.DataFrame, ticker_symbol: str, output_path: str):
    """
    Generates a candlestick chart with technical indicators for a given ticker.
    Optimized for 6-month view and high-visibility squeeze markers.
    """
    # 1. Ensure index is DatetimeIndex and sorted
    if not isinstance(ticker_df.index, pd.DatetimeIndex):
        ticker_df.index = pd.to_datetime(ticker_df.index)
    df = ticker_df.sort_index().copy()
    
    # 2. Ensure Squeeze indicators exist
    if 'Momentum' not in df.columns or 'Squeeze_On' not in df.columns:
        from squeeze.engine.indicators import calculate_squeeze_indicators
        df = calculate_squeeze_indicators(df)

    # 3. Bollinger Bands & Keltner Channels
    bb = df.ta.bbands(length=20, std=2.0)
    kc = df.ta.kc(length=20, scalar=1.5)
    
    # Add to main DF for easy slicing
    df['BB_Upper'] = bb.filter(like='BBU').iloc[:, 0]
    df['BB_Lower'] = bb.filter(like='BBL').iloc[:, 0]
    df['KC_Upper'] = kc.filter(like='KCU').iloc[:, 0]
    df['KC_Lower'] = kc.filter(like='KCL').iloc[:, 0]

    # 4. CRITICAL: Slice to last 6 months (approx 130 bars)
    plot_df = df.tail(130).copy()
    
    # 5. Prepare indicator plots
    plots = [
        # Bollinger Bands (dashed)
        mpf.make_addplot(plot_df['BB_Upper'], color='blue', linestyle='dashed', alpha=0.3),
        mpf.make_addplot(plot_df['BB_Lower'], color='blue', linestyle='dashed', alpha=0.3),
        # Keltner Channels (solid)
        mpf.make_addplot(plot_df['KC_Upper'], color='orange', alpha=0.3),
        mpf.make_addplot(plot_df['KC_Lower'], color='orange', alpha=0.3),
    ]
    
    # 6. Momentum Histogram Colors
    mom = plot_df['Momentum']
    hist_colors = []
    for i in range(len(mom)):
        val = mom.iloc[i]
        prev_val = mom.iloc[i-1] if i > 0 else 0
        if val >= 0:
            hist_colors.append('cyan' if val >= prev_val else 'blue')
        else:
            hist_colors.append('red' if val <= prev_val else 'maroon')
                
    plots.append(mpf.make_addplot(plot_df['Momentum'], type='bar', panel=1, color=hist_colors, 
                                  secondary_y=False, ylabel='Momentum'))
    
    # 7. Squeeze Energy Markers (The dots)
    squeeze_on = plot_df['Squeeze_On']
    energy = plot_df['Energy_Level']
    dot_colors = ['red' if val else 'lime' for val in squeeze_on]
    
    # Scaled sizes for Energy Level 0-3
    dot_sizes = np.array([30 + (e * 100) if s else 30 for s, e in zip(squeeze_on, energy)])
    
    # Plot dots on the zero line of panel 1
    plots.append(mpf.make_addplot(np.zeros(len(plot_df)), type='scatter', markersize=dot_sizes, 
                                  marker='o', color=dot_colors, panel=1, secondary_y=False))

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # 8. Generate Final Plot
    # charles style: green up, red down
    mpf.plot(plot_df, type='candle', style='charles', addplot=plots, 
             title=f"\n{ticker_symbol} - Squeeze Analysis (6mo)", 
             savefig=output_path, volume=True, 
             panel_ratios=(4, 2), 
             datetime_format='%Y-%m',
             xrotation=0,
             show_nontrading=False,
             tight_layout=True)
