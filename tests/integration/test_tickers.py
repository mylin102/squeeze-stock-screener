import pytest
from squeeze.data.tickers import fetch_tickers

def test_fetch_tickers_integration():
    """
    Integration test for fetching tickers from official sources.
    Ensures that we get a list of common stocks including some well-known ones.
    """
    tickers = fetch_tickers()
    
    # Should be a list
    assert isinstance(tickers, list)
    
    # Should have more than 1000 items
    assert len(tickers) > 1000
    
    # Should contain some known tickers with correct suffixes
    assert "2330.TW" in tickers  # TSMC
    assert "2317.TW" in tickers  # Foxconn
    assert "8069.TWO" in tickers #元太 (OTC)
    
    # Tickers should only be digits + suffix
    for t in tickers:
        code, suffix = t.split('.')
        assert code.isdigit()
        assert len(code) == 4
        assert suffix in ["TW", "TWO"]
