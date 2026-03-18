import logging
import pandas as pd
import yfinance as yf
from src.squeeze.core.session import get_robust_session

# Configure logging
logger = logging.getLogger(__name__)

def download_market_data(tickers: list[str], period: str = '1y') -> pd.DataFrame:
    """
    Download daily OHLC data for a list of tickers using yfinance.
    
    Args:
        tickers: List of Taiwan stock tickers (e.g., ["2330.TW"]).
        period: Data period to download (default: '1y').
        
    Returns:
        pd.DataFrame: MultiIndex dataframe grouped by ticker.
    """
    if not tickers:
        logger.warning("No tickers provided for download.")
        return pd.DataFrame()
        
    session = get_robust_session()
    
    try:
        # bulk download
        df = yf.download(
            tickers=tickers,
            period=period,
            interval="1d",
            group_by='ticker',
            threads=True,
            progress=False
        )
        
        if df.empty:
            logger.warning(f"No data found for tickers: {tickers}")
            
        return df
        
    except Exception as e:
        logger.error(f"Error downloading market data: {str(e)}")
        # Return an empty dataframe instead of raising
        return pd.DataFrame()
