import pandas as pd
import requests
import urllib3
import io
from typing import List, Dict

# Suppress InsecureRequestWarning for when verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_tickers() -> List[str]:
    """
    Backward compatibility for existing code.
    """
    mapping = fetch_tickers_with_names()
    return sorted(list(mapping.keys()))

def fetch_tickers_with_names() -> Dict[str, str]:
    """
    Fetch Taiwan tickers and names from TWSE and TPEx.
    Returns a dictionary mapping ticker symbols (.TW/.TWO) to Chinese names.
    """
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "TPEx": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
        "Emerging": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=5",
    }
    
    ticker_map = {}
    
    for market, url in urls.items():
        try:
            response = requests.get(url, verify=False)
            response.encoding = 'big5'
            
            tables = pd.read_html(io.StringIO(response.text))
            df = tables[0]
            
            # Data is in the first column, skipping the header row
            data = df.iloc[1:, 0]
            
            for entry in data:
                if not isinstance(entry, str):
                    continue
                    
                parts = entry.split('\u3000') # Full-width space
                if len(parts) >= 2:
                    code = parts[0].strip()
                    name = parts[1].strip()
                    if len(code) == 4 and code.isdigit():
                        # yfinance suffixes: .TW for TWSE, .TWO for TPEx and Emerging
                        suffix = ".TW" if market == "TWSE" else ".TWO"
                        ticker_map[f"{code}{suffix}"] = name
        except Exception as e:
            print(f"Error fetching {market} stocks: {e}")
                    
    return ticker_map
