"""Squeeze TW Chart — Modal serverless deployment.
Deploy:  modal deploy modal_app.py
Usage:   https://<workspace>--squeeze-tw-chart-generate.modal.run?ticker=2303
"""
import sys
from pathlib import Path as _Path
_root = _Path(__file__).parent
sys.path.insert(0, str(_root / "src"))

import modal
import base64

app = modal.App("squeeze-tw-chart")

# Build a container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "yfinance>=0.2", "pandas>=2.0", "pandas-ta>=0.3",
        "requests>=2.31", "matplotlib>=3.7", "mplfinance>=0.12",
        "scipy>=1.11", "lxml>=4.9", "html5lib>=1.1", "jinja2>=3.1",
        "typer>=0.9", "rich>=13.0", "tenacity>=8.0",
    )
    .add_local_dir(str(_root / "src"), "/root/src")
)


@app.function(image=image, timeout=120)
@modal.fastapi_endpoint(method="GET", docs=True)
def generate(ticker: str = "2303", period: str = "1y"):
    """Generate a Squeeze TW chart for any Taiwan stock ticker."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    from squeeze.engine.scanner import MarketScanner
    from squeeze.report.visualizer import plot_ticker
    from squeeze.data.tickers import fetch_tickers_with_names
    from squeeze.cli import _normalize_tw_ticker

    ticker = ticker.strip().upper()
    try:
        ticker_map = fetch_tickers_with_names()
        normalized = _normalize_tw_ticker(ticker, ticker_map)
        display_name = ticker_map.get(normalized, normalized)

        scanner = MarketScanner([normalized], ticker_names=ticker_map)
        scanner.fetch_data(period=period)

        if scanner.data.empty:
            return {"error": f"No data for {normalized}"}

        bm_close = None
        scanner.fetch_benchmark(period=period)
        bm_close = scanner.benchmark_close if not scanner.benchmark_close.empty else None

        if isinstance(scanner.data.columns, pd.MultiIndex):
            ticker_df = scanner.data[normalized].dropna(subset=["Close"])
        else:
            ticker_df = scanner.data.dropna(subset=["Close"])

        if ticker_df.empty:
            return {"error": f"No plottable data for {normalized}"}

        # Generate chart to temp file
        _tmp_chart = _Path("/tmp") / f"{normalized}_chart.png"
        plot_ticker(
            ticker_df=ticker_df,
            ticker_symbol=normalized,
            output_path=str(_tmp_chart),
            benchmark_close=bm_close,
        )
        if _tmp_chart.exists():
            img_b64 = base64.b64encode(_tmp_chart.read_bytes()).decode()
            _tmp_chart.unlink(missing_ok=True)
        else:
            return {"error": "Chart generation failed"}

        last = ticker_df.iloc[-1]
        prev = ticker_df.iloc[-2] if len(ticker_df) > 1 else last

        return {
            "ticker": normalized,
            "name": display_name,
            "period": period,
            "last_close": float(last["Close"]),
            "change": float(last["Close"] - prev["Close"]),
            "high": float(last["High"]),
            "low": float(last["Low"]),
            "volume": int(last.get("Volume", 0)),
            "date_from": str(ticker_df.index[0].date()),
            "date_to": str(ticker_df.index[-1].date()),
            "chart_png_base64": img_b64,
        }

    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}
