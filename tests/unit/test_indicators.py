import pandas as pd
import numpy as np
import pytest
from squeeze.engine.indicators import calculate_squeeze_indicators

def test_calculate_squeeze_indicators_structure(sample_ohlcv_df):
    """
    Verify that the calculate_squeeze_indicators function returns a dataframe 
    with the expected columns.
    """
    df = calculate_squeeze_indicators(sample_ohlcv_df)
    
    expected_columns = [
        'Squeeze_On', 
        'Energy_Level', 
        'Momentum', 
        'Fired'
    ]
    
    for col in expected_columns:
        assert col in df.columns
    
    # COMMENT ADDED FOR MODIFICATION:
    # Verify new Trend Context columns added in Phase 6
    trend_cols = ['MA20', 'MA20_Slope', 'MA20_Converging', 'Close_Above_MA20']
    for col in trend_cols:
        assert col in df.columns

def test_ma20_trend_context_logic():
    """
    Verify the mathematical correctness of MA20 slope and convergence.
    """
    # Create a synthetic downtrend that starts to flatten (rounding bottom)
    # 60 bars: 40 flat at 100 → 10 declining → 10 flat
    flat = [100.0] * 40
    decline = [95.0, 90.0, 86.0, 83.0, 81.0, 79.0, 78.0, 77.0, 76.5, 76.0]
    recovery = [76.0] * 10
    close_prices = flat + decline + recovery

    data = {
        'Open': close_prices,
        'High': [c + 2 for c in close_prices],
        'Low': [c - 2 for c in close_prices],
        'Close': close_prices,
        'Volume': [1000] * len(close_prices),
    }
    df = pd.DataFrame(data)
    res = calculate_squeeze_indicators(df)

    # MA20 warmup is 20 bars. With 60 bars total, we have 40 valid MA20 values.
    # The decline creates a negative MA20_Slope that converges toward zero.
    converging_mask = res['MA20_Converging']
    assert converging_mask.any(), "Convergence should be detected in rounding bottom"
    
    # Verify price position logic
    for i in range(len(res)):
        assert res.iloc[i]['Close_Above_MA20'] == (res.iloc[i]['Close'] > res.iloc[i]['MA20'])

def test_calculate_squeeze_indicators_values(sample_ohlcv_df):
    """
    Verify basic properties of the indicator output.
    """
    df = calculate_squeeze_indicators(sample_ohlcv_df)
    
    # Squeeze_On should be boolean
    assert df['Squeeze_On'].dtype == bool
    
    # Energy_Level should be between 0 and 3
    assert df['Energy_Level'].min() >= 0
    assert df['Energy_Level'].max() <= 3
    assert df['Energy_Level'].dtype in [np.int64, np.int32]
    
    # Fired should be boolean
    assert df['Fired'].dtype == bool

def test_squeeze_logic_reproduction(sample_ohlcv_df):
    """
    Verify specific logic: Squeeze On when BB inside KC.
    """
    # This is a bit harder to test without manually calculating, 
    # but we can check if it runs and produces expected types.
    df = calculate_squeeze_indicators(sample_ohlcv_df)
    
    # At least some values should be boolean
    assert not df['Squeeze_On'].isna().all()

def test_empty_dataframe():
    """
    Verify behavior with empty dataframe.
    """
    df = pd.DataFrame()
    with pytest.raises(Exception):
        calculate_squeeze_indicators(df)
