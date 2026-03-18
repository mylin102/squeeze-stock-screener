import pandas as pd
import yfinance as yf
import logging
from typing import List, Dict, Any
from src.squeeze.core.session import get_robust_session

logger = logging.getLogger(__name__)

def get_fundamentals(tickers: List[str]) -> pd.DataFrame:
    """
    Fetch fundamental data for a list of tickers using yfinance.
    
    Args:
        tickers: List of Taiwan stock tickers (e.g., ["2330.TW"]).
        
    Returns:
        pd.DataFrame: Fundamental metrics for each ticker.
    """
    if not tickers:
        logger.warning("No tickers provided for fundamental fetching.")
        return pd.DataFrame()

    session = get_robust_session()
    results = []
    
    # yf.Tickers allows for some batching efficiency
    yf_tickers = yf.Tickers(" ".join(tickers))
    
    for ticker_symbol in tickers:
        try:
            ticker_obj = yf_tickers.tickers[ticker_symbol]
            info = ticker_obj.info
            
            results.append({
                'ticker': ticker_symbol,
                'marketCap': info.get('marketCap'),
                'trailingPE': info.get('trailingPE'),
                'priceToBook': info.get('priceToBook'),
                'dividendYield': info.get('dividendYield'),
                'averageVolume': info.get('averageVolume'),
                'sector': info.get('sector')
            })
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ticker_symbol}: {str(e)}")
            results.append({
                'ticker': ticker_symbol,
                'error': str(e)
            })
            
    return pd.DataFrame(results)
