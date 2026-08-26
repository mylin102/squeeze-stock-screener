import logging
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
from typing import Callable, List, Dict, Any, Optional
import numpy as np
import yfinance as yf
from squeeze.data.downloader import download_market_data
from squeeze.data.fundamentals import get_fundamentals
from squeeze.engine.ranker import calculate_value_score, enrich_with_scores

TAIEX_TICKER = "^TWII"

# Configure logging
logger = logging.getLogger(__name__)

class MarketScanner:
    """
    MarketScanner handles high-performance market-wide scanning for patterns.
    Uses a hybrid approach:
    - Threading for I/O bound data fetching (via yfinance).
    - Multiprocessing for CPU bound pattern detection.
    """
    
    def __init__(self, tickers: List[str], ticker_names: Optional[Dict[str, str]] = None):
        """
        Initialize the scanner with a list of tickers.
        
        Args:
            tickers: List of ticker strings (e.g., ["2330.TW", "2317.TW"]).
            ticker_names: Optional dictionary mapping ticker to Chinese name.
        """
        self.tickers = tickers
        self.ticker_names = ticker_names or {}
        self.data: pd.DataFrame = pd.DataFrame()
        self.fundamentals: pd.DataFrame = pd.DataFrame()
        self.benchmark_close: pd.Series = pd.Series(dtype=float)
        self.benchmark_metadata: Dict[str, Any] = {
            "benchmark_symbol": TAIEX_TICKER,
            "benchmark_source": "yfinance",
        }
        self._scan_id: str = ""
        self.results: List[Dict[str, Any]] = []

    def fetch_data(self, period: str = "2y", data: pd.DataFrame = None):
        """
        Fetch market data for all tickers or use provided data.
        """
        if data is not None:
            self.data = data
            return self.data
            
        logger.info(f"Fetching data for {len(self.tickers)} tickers...")
        self.data = download_market_data(self.tickers, period=period)
        return self.data

    def fetch_benchmark(self, period: str = "2y", ticker: str = TAIEX_TICKER) -> pd.Series:
        """Fetch benchmark (TAIEX ^TWII) close prices for RS calculation."""
        logger.info(f"Fetching benchmark {ticker}...")
        self.benchmark_metadata["benchmark_period"] = period
        try:
            bm_df = yf.download(ticker, period=period, interval="1d", progress=False)
            if bm_df is not None and not bm_df.empty:
                if "Close" in bm_df.columns:
                    self.benchmark_close = bm_df["Close"].squeeze()
                elif "Adj Close" in bm_df.columns:
                    self.benchmark_close = bm_df["Adj Close"].squeeze()
                # Record the last available benchmark date
                if isinstance(self.benchmark_close, pd.Series) and not self.benchmark_close.empty:
                    self.benchmark_metadata["benchmark_last_date"] = str(self.benchmark_close.index[-1].date())
        except Exception as e:
            logger.warning(f"Failed to fetch benchmark {ticker}: {e}")
        return self.benchmark_close

    def fetch_fundamentals(self):
        """
        Fetch fundamental data for all tickers and calculate Value Score.
        """
        logger.info(f"Fetching fundamentals for {len(self.tickers)} tickers...")
        try:
            raw_fundamentals = get_fundamentals(self.tickers)
            if not raw_fundamentals.empty:
                self.fundamentals = calculate_value_score(raw_fundamentals)
        except Exception as e:
            logger.error(f"Fundamental fetch failed (continuing without): {e}")
            self.fundamentals = pd.DataFrame()
        return self.fundamentals

    def scan(self, 
             pattern_fn: Callable[[pd.DataFrame], Dict[str, Any]], 
             min_mkt_cap: Optional[float] = None,
             min_avg_volume: Optional[float] = None,
             min_score: Optional[float] = None,
             benchmark_close: Optional[pd.Series] = None) -> List[Dict[str, Any]]:
        """
        Scan the downloaded market data for a given pattern and apply fundamental filters.

        Volume filtering (min_avg_volume) is applied in two stages:
        - Stage 1 (fundamentals path): filters via yfinance 'averageVolume' field
          when fundamentals have been fetched (fetch_fundamentals() was called).
        - Stage 2 (OHLCV path): ALWAYS applies min_avg_volume using the 20-day average
          of the downloaded Volume column, independent of fundamentals. This ensures
          low-liquidity stocks (< min_avg_volume shares/day) are always excluded even
          when fundamentals are not fetched.

        Args:
            pattern_fn: Pattern detection function to apply to each ticker's OHLCV DataFrame.
            min_mkt_cap: Minimum market cap (in TWD). Requires fundamentals.
            min_avg_volume: Minimum average daily volume (in shares, NOT lots).
                            e.g. 500 lots = 500_000 shares.
                            Applied from OHLCV data (always) and fundamentals (if available).
            min_score: Minimum value score. Requires fundamentals.
            benchmark_close: Optional benchmark (e.g. TAIEX) close series for RS calculation.
        """
        if self.data.empty:
            logger.warning("No data to scan. Call fetch_data() first.")
            return []

        # ── Step 1: Fundamental-based filters (only when fundamentals are available) ──
        filtered_tickers = set(self.tickers)
        fundamental_map = {}

        if not self.fundamentals.empty:
            df_fund = self.fundamentals.copy()

            # Apply fundamental filters
            if min_mkt_cap is not None:
                df_fund = df_fund[df_fund['marketCap'] >= min_mkt_cap]
            if min_avg_volume is not None:
                # fundamentals averageVolume is already in shares
                df_fund = df_fund[df_fund['averageVolume'] >= min_avg_volume]
            if min_score is not None:
                df_fund = df_fund[df_fund['value_score'] >= min_score]

            filtered_tickers = set(df_fund['ticker'].tolist())
            # Create a map for easy lookup later
            fundamental_map = df_fund.set_index('ticker').to_dict('index')
            logger.info(
                f"Fundamental filtering reduced tickers from {len(self.tickers)} to {len(filtered_tickers)}"
            )

        # ── Step 2: Build ticker tasks with OHLCV-based volume filter ─────────────────
        # This filter runs regardless of whether fundamentals were fetched, so
        # min_avg_volume is always honoured even in fundamentals-free mode.
        _VOLUME_LOOKBACK = 20  # trading days for avg volume calculation
        tasks = []

        if len(self.tickers) == 1:
            # Single-ticker mode: data is a flat DataFrame, not MultiIndex
            ticker = self.tickers[0]
            if ticker in filtered_tickers and not self.data.empty:
                tasks.append((ticker, self.data))
        else:
            for ticker in filtered_tickers:
                try:
                    if ticker not in self.data.columns.get_level_values(0):
                        continue
                    ticker_df = self.data[ticker].dropna(subset=['Close'])
                    if ticker_df.empty:
                        continue

                    # OHLCV-based volume filter: skip if recent avg volume is too low
                    if min_avg_volume is not None and 'Volume' in ticker_df.columns:
                        recent_vol = ticker_df['Volume'].tail(_VOLUME_LOOKBACK)
                        avg_vol = recent_vol.mean()
                        if pd.isna(avg_vol) or avg_vol < min_avg_volume:
                            logger.debug(
                                f"Skipping {ticker}: avg 20d volume {avg_vol:,.0f} < {min_avg_volume:,.0f}"
                            )
                            continue

                    tasks.append((ticker, ticker_df))
                except (KeyError, AttributeError):
                    continue

        if not tasks:
            logger.warning("No valid ticker data found to scan after filtering.")
            return []

        # 3. Pattern Detection (Multiprocessing)
        results = []
        # Generate a stable scan_id for this batch
        from datetime import datetime
        self._scan_id = datetime.now().strftime("scan_%Y%m%d_%H%M%S")
        # Bind benchmark_close to pattern_fn if available (partial is picklable)
        if benchmark_close is not None and not benchmark_close.empty:
            wrapped_fn = partial(pattern_fn, benchmark_close=benchmark_close)
        else:
            wrapped_fn = pattern_fn
        with ProcessPoolExecutor() as executor:
            future_to_ticker = {executor.submit(wrapped_fn, df): ticker for ticker, df in tasks}
            
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    result = future.result()
                    result['ticker'] = ticker
                    result['name'] = self.ticker_names.get(ticker, "未知")
                    
                    # Merge fundamental data into results
                    if ticker in fundamental_map:
                        result.update(fundamental_map[ticker])
                        
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error scanning ticker {ticker}: {str(e)}")
                    results.append({
                        'ticker': ticker,
                        'name': self.ticker_names.get(ticker, "未知"),
                        'error': str(e),
                        'is_squeezed': False
                    })
        
        self.results = enrich_with_scores(results)
        # Attach benchmark metadata + scan_id to each result
        for r in self.results:
            r.update(self.benchmark_metadata)
            r["scan_id"] = self._scan_id
        return self.results
