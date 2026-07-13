import pandas as pd
import mplfinance as mpf
import pandas_ta as ta
import numpy as np
import os
import matplotlib
import matplotlib.pyplot as plt
from squeeze.engine.indicators import add_rs_indicators, TAIEX_TICKER
import yfinance as yf

# ---------------------------------------------------------------------------
# Chinese font setup — works on macOS (local) and Ubuntu (GitHub Actions)
# ---------------------------------------------------------------------------
def _setup_cjk_font() -> str:
    """Find or download a CJK font for matplotlib. Returns the font name."""
    # 1. Check known system CJK fonts
    candidates = [
        "Noto Sans CJK JP",      # Ubuntu after apt install fonts-noto-cjk
        "Noto Sans CJK SC",      # Ubuntu alt name
        "Noto Sans TC",          # macOS / manual install
        "WenQuanYi Micro Hei",   # Ubuntu default CJK
        "WenQuanYi Zen Hei",
        "Source Han Sans TW",
        "Source Han Sans SC",
        "PingFang TC",           # macOS
        "STHeiti",               # macOS
        "Microsoft JhengHei",    # Windows
        "SimHei",                # Windows
        "AR PL UMing TW",        # Linux
    ]
    available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name

    # 2. Try to download Noto Sans CJK (GitHub Actions fallback)
    try:
        import urllib.request
        import zipfile
        import shutil
        cache_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".font_cache")
        os.makedirs(cache_dir, exist_ok=True)
        font_path = os.path.join(cache_dir, "NotoSansCJKsc-Regular.otf")
        if not os.path.exists(font_path):
            url = ("https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/"
                   "simplified-chinese/NotoSansCJKsc-Regular.otf")
            urllib.request.urlretrieve(url, font_path)
        if os.path.exists(font_path):
            matplotlib.font_manager.fontManager.addfont(font_path)
            return "Noto Sans CJK SC"
    except Exception:
        pass

    return "sans-serif"  # fallback


_CJK_FONT = _setup_cjk_font()
matplotlib.rcParams["font.family"] = _CJK_FONT
matplotlib.rcParams["axes.unicode_minus"] = False


def plot_ticker(ticker_df: pd.DataFrame, ticker_symbol: str, output_path: str,
                benchmark_close: pd.Series | None = None):
    """
    Generates a candlestick chart with technical indicators for a given ticker.
    If benchmark_close is provided, an RS (Relative Strength) panel is added.

    Optimized: 1-year view, separate Squeeze State and RS panels.
    """
    # 1. Ensure index is DatetimeIndex and sorted
    if not isinstance(ticker_df.index, pd.DatetimeIndex):
        ticker_df.index = pd.to_datetime(ticker_df.index)
    df = ticker_df.sort_index().copy()

    # 2. Ensure Squeeze indicators exist
    if 'Momentum' not in df.columns or 'Squeeze_On' not in df.columns:
        from squeeze.engine.indicators import calculate_squeeze_indicators
        df = calculate_squeeze_indicators(df)

    # 2b. Add RS indicators if benchmark is provided
    has_rs = False
    if benchmark_close is not None and not benchmark_close.empty:
        df = add_rs_indicators(df, benchmark_close)
        has_rs = True

    # 3. Bollinger Bands & Keltner Channels
    bb = df.ta.bbands(length=20, std=2.0)
    kc = df.ta.kc(length=20, scalar=1.5)

    df['BB_Upper'] = bb.filter(like='BBU').iloc[:, 0]
    df['BB_Lower'] = bb.filter(like='BBL').iloc[:, 0]
    df['KC_Upper'] = kc.filter(like='KCU').iloc[:, 0]
    df['KC_Lower'] = kc.filter(like='KCL').iloc[:, 0]

    # 4. Slice to last 1 year (approx 252 trading days)
    plot_df = df.tail(252).copy()

    # 5. Prepare indicator plots
    plots = [
        # Main Panel (Panel 0): Channels
        mpf.make_addplot(plot_df['BB_Upper'], color='blue', linestyle='dashed', alpha=0.2),
        mpf.make_addplot(plot_df['BB_Lower'], color='blue', linestyle='dashed', alpha=0.2),
        mpf.make_addplot(plot_df['KC_Upper'], color='orange', alpha=0.2),
        mpf.make_addplot(plot_df['KC_Lower'], color='orange', alpha=0.2),
    ]

    # 6. Panel 1: Momentum Histogram
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

    # 7. Panel 2: Squeeze Status Ribbon (High Visibility)
    squeeze_on = plot_df['Squeeze_On']
    status_val = np.full(len(plot_df), 1.0)
    status_colors = np.where(squeeze_on, 'black', '#cccccc')
    plots.append(mpf.make_addplot(status_val, type='bar', panel=2, color=status_colors,
                                  width=1.0, secondary_y=False, ylabel='SQZ'))

    # 8. Panel 3: RS (if benchmark available)
    panel_ratios = (6, 2, 1)
    if has_rs and 'RS_Index' in plot_df.columns:
        rs_index = plot_df['RS_Index']
        rs_ema20 = plot_df['RS_EMA20']
        rs_ema60 = plot_df['RS_EMA60']
        # Convert EMA values to index scale for overlay
        base_ratio = plot_df['RS_Ratio'].iloc[0] if 'RS_Ratio' in plot_df.columns and not plot_df['RS_Ratio'].empty and plot_df['RS_Ratio'].iloc[0] != 0 else 1.0
        ema20_index = (rs_ema20 / base_ratio) * 100.0
        ema60_index = (rs_ema60 / base_ratio) * 100.0

        plots.append(mpf.make_addplot(rs_index, panel=3, color='purple', width=1.0,
                                      secondary_y=False, ylabel='RS Index'))
        plots.append(mpf.make_addplot(ema20_index, panel=3, color='red', width=0.8,
                                      alpha=0.7, secondary_y=False))
        plots.append(mpf.make_addplot(ema60_index, panel=3, color='blue', width=0.8,
                                      alpha=0.5, secondary_y=False))
        panel_ratios = (6, 2, 1, 2)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # 9. Find first trading day of each month for exact monthly tick placement
    # Since show_nontrading=False is used, the x-axis values are integer indices.
    # We find the start index of each month in plot_df's index.
    month_starts = []
    month_labels = []
    seen_months = set()
    for idx, date in enumerate(plot_df.index):
        month_key = (date.year, date.month)
        if month_key not in seen_months:
            seen_months.add(month_key)
            month_starts.append(idx)
            month_labels.append(date.strftime("%Y-%m"))

    # Generate Final Plot with returnfig=True to allow customizing axis ticks
    # Added comments to comply with user rule in GEMINI.md
    fig, axlist = mpf.plot(plot_df, type='candle', style='charles', addplot=plots,
                           title=f"\n{ticker_symbol} - Squeeze Analysis (1yr)",
                           volume=True,
                           panel_ratios=panel_ratios,
                           xrotation=0,
                           show_nontrading=False,
                           tight_layout=True,
                           returnfig=True)

    # Explicitly set monthly ticks and labels on the shared x-axis
    axlist[0].set_xticks(month_starts)
    axlist[0].set_xticklabels(month_labels)

    # Enable gridlines on all axes that have visible x-axis grids
    for ax in axlist:
        if ax.xaxis.get_visible():
            ax.grid(True, which='both', axis='x', color='gray', linestyle='--', alpha=0.3)

    # Save the configured figure to output_path
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)

