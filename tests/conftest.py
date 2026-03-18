import pytest
import pandas as pd
import numpy as np

@pytest.fixture
def sample_ohlcv_df():
    """
    Returns a sample OHLCV dataframe for testing indicators.
    Contains 100 days of synthetic data.
    """
    dates = pd.date_range(start="2023-01-01", periods=100)
    data = {
        "Open": np.random.uniform(100, 110, 100),
        "High": np.random.uniform(110, 120, 100),
        "Low": np.random.uniform(90, 100, 100),
        "Close": np.random.uniform(100, 110, 100),
        "Volume": np.random.uniform(1000, 5000, 100),
    }
    df = pd.DataFrame(data, index=dates)
    # Ensure High is highest and Low is lowest
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df

@pytest.fixture
def mock_tickers():
    """
    Returns a small list of mock tickers for testing.
    """
    return ["2330.TW", "2317.TW", "8069.TWO", "0050.TW"]
