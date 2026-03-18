import yfinance as yf
import json

tickers = ["2330.TW", "2317.TW", "6547.TWO"] # TSMC, Foxconn, and a TPEx stock

for ticker in tickers:
    print(f"--- {ticker} ---")
    t = yf.Ticker(ticker)
    info = t.info
    # Just print some keys to see what's available
    relevant_keys = [
        "marketCap", "averageVolume", "sector", "industry", 
        "trailingPE", "forwardPE", "priceToBook", "dividendYield",
        "trailingEps", "forwardEps", "bookValue", "enterpriseValue",
        "totalRevenue", "profitMargins", "operatingMargins"
    ]
    data = {k: info.get(k) for k in relevant_keys if k in info}
    print(json.dumps(data, indent=2))
