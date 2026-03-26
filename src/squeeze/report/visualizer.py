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
        # Avoid circular import if possible, but for simplicity:
        from squeeze.engine.indicators import calculate_squeeze_indicators
        df = calculate_squeeze_indicators(df)

    plots = [
        # Bollinger Bands (dashed)
        mpf.make_addplot(bb_upper, color='blue', linestyle='dashed', alpha=0.3),
        mpf.make_addplot(bb_lower, color='blue', linestyle='dashed', alpha=0.3),
        # Keltner Channels (solid)
        mpf.make_addplot(kc_upper, color='orange', alpha=0.3),
        mpf.make_addplot(kc_lower, color='orange', alpha=0.3),
    ]
    
    # Squeeze Momentum Histogram colors
    mom = df['Momentum']
    hist_colors = []
    for i in range(len(mom)):
        val = mom.iloc[i]
        prev_val = mom.iloc[i-1] if i > 0 else 0
        
        if val >= 0:
            if val >= prev_val:
                hist_colors.append('cyan')
            else:
                hist_colors.append('blue')
        else:
            if val <= prev_val:
                hist_colors.append('red')
            else:
                hist_colors.append('maroon')
                
    plots.append(mpf.make_addplot(df['Momentum'], type='bar', panel=1, color=hist_colors, secondary_y=False))
    
    # Squeeze Dots (Red when Squeeze_On is True, Green when False)
    squeeze_on = df['Squeeze_On']
    dot_colors = ['black' if val else 'silver' for val in squeeze_on]
    # Plot dots at 0 on the momentum panel
    plots.append(mpf.make_addplot(np.zeros(len(df)), type='scatter', markersize=40, marker='o', 
                                  color=dot_colors, panel=1, secondary_y=False))

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Generate Plot
    mpf.plot(df, type='candle', style='charles', addplot=plots, 
             title=f"{ticker_symbol} - Squeeze Analysis", 
             savefig=output_path, volume=True, 
             panel_ratios=(4, 2), # Main plot and Indicators
             show_nontrading=False,
             tight_layout=True)
