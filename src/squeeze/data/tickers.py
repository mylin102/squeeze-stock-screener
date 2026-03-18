import pandas as pd
import requests
import urllib3
import io
from typing import List

# Suppress InsecureRequestWarning for when verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_tickers() -> List[str]:
    """
    Fetch Taiwan tickers from TWSE and TPEx official ISIN sources.
    Returns a list of ticker symbols with .TW or .TWO suffix.
    """
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "TPEx": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
    }
    
    all_tickers = []
    
    for market, url in urls.items():
        # Fetch the page with correct encoding
        # verify=False is needed due to 'Missing Subject Key Identifier' SSL error on some environments
        response = requests.get(url, verify=False)
        response.encoding = 'big5'
        
        # Parse the HTML tables
        # Use io.StringIO to avoid pandas interpreting the HTML string as a file path
        tables = pd.read_html(io.StringIO(response.text))
        
        # The main table is usually the first (and only) one
        df = tables[0]
        
        # The table format is usually:
        # Col 0: 有價證券代號及名稱 (Security Code and Name, e.g., "1101　台泥")
        # Col 1: ISIN Code
        # Col 2: 上市日 (Listing Date)
        # Col 3: 市場別 (Market Type)
        # Col 4: 產業別 (Industry Type)
        # Col 5: CFICode
        # Col 6: 備註 (Remarks)
        
        # We only care about column 0
        # Filter for rows where column 0 starts with a 4-digit code followed by a space
        # Then extract that 4-digit code.
        
        # Skip the first row (header-like)
        data = df.iloc[1:, 0]
        
        for entry in data:
            if not isinstance(entry, str):
                continue
                
            parts = entry.split('\u3000') # Full-width space
            if len(parts) >= 1:
                code = parts[0].strip()
                if len(code) == 4 and code.isdigit():
                    suffix = ".TW" if market == "TWSE" else ".TWO"
                    all_tickers.append(f"{code}{suffix}")
                    
    return sorted(list(set(all_tickers)))
