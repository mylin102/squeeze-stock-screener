import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_squeeze_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate PowerSqueeze indicators using pandas-ta and custom logic.
    
    Args:
        df: DataFrame with OHLCV data.
        
    Returns:
        pd.DataFrame: Original DataFrame with added squeeze indicators.
    """
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    # 1. Standard TTM Squeeze using pandas-ta
    # This provides SQZ_ON, SQZ_OFF, and Momentum (SQZ_...)
    sqz = df.ta.squeeze(bb_length=20, bb_std=2.0, kc_length=20, kc_scalar=1.5, lazy=True)
    
    # Identify columns (naming varies by params)
    sqz_on_col = [c for c in sqz.columns if 'SQZ_ON' in c][0]
    mom_col = [c for c in sqz.columns if c.startswith('SQZ_') and c not in ['SQZ_ON', 'SQZ_OFF', 'SQZ_NO']][0]
    
    # 2. Custom Energy Level Calculation (from legacy logic)
    # We still need BB and KC widths for the squeeze ratio
    bb = df.ta.bbands(length=20, std=2.0)
    kc = df.ta.kc(length=20, scalar=1.5)
    
    bb_upper = bb.filter(like='BBU').iloc[:, 0]
    bb_lower = bb.filter(like='BBL').iloc[:, 0]
    kc_upper = kc.filter(like='KCU').iloc[:, 0]
    kc_lower = kc.filter(like='KCL').iloc[:, 0]
    
    bb_width = bb_upper - bb_lower
    kc_width = kc_upper - kc_lower
    
    # Energy level: compression ratio
    squeeze_ratio = (kc_width - bb_width) / kc_width
    squeeze_ratio = squeeze_ratio.clip(lower=0, upper=1)
    
    energy_level = pd.cut(
        squeeze_ratio, 
        bins=[-np.inf, 0.3, 0.5, 0.7, np.inf], 
        labels=[0, 1, 2, 3]
    ).fillna(0).astype(int)
    
    # 3. Assemble Results
    result = df.copy()
    result['Squeeze_On'] = sqz[sqz_on_col].astype(bool)
    result['Energy_Level'] = energy_level
    result['Momentum'] = sqz[mom_col].fillna(0)
    
    # Fired: Not squeezed now but was squeezed in the previous bar
    result['Fired'] = (~result['Squeeze_On']) & (result['Squeeze_On'].shift(1) == True)
    result['Fired'] = result['Fired'].fillna(False)
    
    return result
