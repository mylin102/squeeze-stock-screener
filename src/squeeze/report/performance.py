import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import logging
from squeeze.data.downloader import download_market_data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
# New columns (v2 schema) — old CSV rows get defaults via normalize_tracking_df.
# Keeping all original columns for backward compat.
TRACKING_COLUMNS = [
    # --- identity ---
    'date', 'ticker', 'name',
    # --- entry ---
    'entry_price', 'signal', 'signal_score',
    # --- pattern booleans ---
    'has_squeeze', 'has_houyi', 'has_whale',
    # --- MA20 ---
    'close_above_ma20', 'ma20_slope', 'ma20_converging',
    # --- volume ---
    'volume_expansion', 'volume_expansion_ratio',
    # --- RS (raw values for later bucketing) ---
    'rs_ratio', 'rs_slope_5d', 'rs_new_high_60',
    # --- scores ---
    'ranking_score', 'experimental_score', 'rs_component_score',
    'ranking_score_version', 'feature_schema_version', 'feature_schema_date',
    'scan_id',
    'rank_position_v1', 'ranking_percentile_v1',
    'rank_position_v2', 'ranking_percentile_v2',
    # --- return windows ---
    'return_5d', 'return_10d', 'return_14d', 'return_20d',
    'max_favorable_excursion_14d', 'max_adverse_excursion_14d',
    'hit_5pct_14d', 'days_to_peak_14d',
    'drawdown_before_hit_5pct', 'hit_5pct_before_minus_5pct',
    # --- legacy / tracking ---
    'current_price', 'return_pct', 'strategy_return_pct', 'days_tracked',
    'last_updated', 'status', 'type', 'pattern', 'momentum',
    'prev_momentum', 'energy_level', 'squeeze_on', 'fired',
    'market_regime', 'benchmark_ticker', 'value_score',
    'benchmark_symbol', 'benchmark_period', 'benchmark_source',
    'benchmark_last_date',
    # --- stop loss ---
    'stop_loss_rule', 'stop_loss_threshold', 'stop_loss_triggered',
    'stop_loss_message', 'stop_loss_ma_window', 'stop_loss_ticks',
    'stop_loss_tick_size',
]

# Defaults for new v2 columns — old CSVs that lack them get np.nan (not False/0)
# to avoid polluting statistics with fabricated negative signals.
_NEW_COL_DEFAULTS = {
    'signal_score': np.nan,
    'has_squeeze': np.nan,
    'has_houyi': np.nan,
    'has_whale': np.nan,
    'close_above_ma20': np.nan,
    'ma20_slope': np.nan,
    'ma20_converging': np.nan,
    'volume_expansion': np.nan,
    'volume_expansion_ratio': np.nan,
    'rs_ratio': np.nan,
    'rs_slope_5d': np.nan,
    'rs_new_high_60': np.nan,
    'ranking_score': np.nan,
    'rs_component_score': np.nan,
    'experimental_score': np.nan,
    'ranking_score_version': np.nan,
    'feature_schema_version': np.nan,
    'feature_schema_date': np.nan,
    'scan_id': np.nan,
    'rank_position_v1': np.nan,
    'ranking_percentile_v1': np.nan,
    'rank_position_v2': np.nan,
    'ranking_percentile_v2': np.nan,
    # Legacy compat aliases
    'composite_score': np.nan,
    'composite_score_v2': np.nan,
    'score_version': np.nan,
    'return_5d': np.nan,
    'return_10d': np.nan,
    'return_14d': np.nan,
    'return_20d': np.nan,
    'max_favorable_excursion_14d': np.nan,
    'max_adverse_excursion_14d': np.nan,
    'hit_5pct_14d': np.nan,
    'days_to_peak_14d': np.nan,
    'drawdown_before_hit_5pct': np.nan,
    'hit_5pct_before_minus_5pct': np.nan,
    # Legacy compat aliases
    'rs_value': np.nan,
    'rs_slope': np.nan,
    'max_return_14d': np.nan,
    'max_drawdown_14d': np.nan,
    'rank_position': np.nan,
    'ranking_percentile': np.nan,
    # Benchmark metadata
    'benchmark_symbol': np.nan,
    'benchmark_period': np.nan,
    'benchmark_source': np.nan,
    'benchmark_last_date': np.nan,
}


def normalize_tracking_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise a loaded CSV to the full column set — backward compat."""
    if df is None or df.empty:
        return pd.DataFrame(columns=TRACKING_COLUMNS)

    normalized = df.copy()
    # Legacy defaults
    legacy_defaults = {
        'strategy_return_pct': None,
        'type': 'buy',
        'pattern': 'squeeze',
        'momentum': 0.0,
        'prev_momentum': 0.0,
        'energy_level': 0,
        'squeeze_on': False,
        'fired': False,
        'market_regime': 'unknown',
        'benchmark_ticker': '^TWII',
        'value_score': None,
        'stop_loss_rule': None,
        'stop_loss_threshold': None,
        'stop_loss_triggered': False,
        'stop_loss_message': None,
        'stop_loss_ma_window': None,
        'stop_loss_ticks': 0,
        'stop_loss_tick_size': 0.01,
    }
    for column in TRACKING_COLUMNS:
        if column not in normalized.columns:
            default = _NEW_COL_DEFAULTS.get(column, legacy_defaults.get(column, None))
            normalized[column] = default

    # Type coercion for legacy fields
    normalized['return_pct'] = pd.to_numeric(normalized['return_pct'], errors='coerce').fillna(0.0)
    normalized['strategy_return_pct'] = pd.to_numeric(normalized['strategy_return_pct'], errors='coerce')
    missing_strategy = normalized['strategy_return_pct'].isna()
    normalized.loc[missing_strategy, 'strategy_return_pct'] = normalized.loc[missing_strategy].apply(
        lambda row: -row['return_pct'] if row.get('type') == 'sell' else row['return_pct'],
        axis=1,
    )
    normalized['days_tracked'] = pd.to_numeric(normalized['days_tracked'], errors='coerce').fillna(0).astype(int)
    normalized['momentum'] = pd.to_numeric(normalized['momentum'], errors='coerce').fillna(0.0)
    normalized['prev_momentum'] = pd.to_numeric(normalized['prev_momentum'], errors='coerce').fillna(0.0)
    normalized['energy_level'] = pd.to_numeric(normalized['energy_level'], errors='coerce').fillna(0).astype(int)
    normalized['squeeze_on'] = normalized['squeeze_on'].apply(lambda v: bool(v) if pd.notna(v) else False)
    normalized['fired'] = normalized['fired'].apply(lambda v: bool(v) if pd.notna(v) else False)
    normalized['stop_loss_threshold'] = pd.to_numeric(normalized['stop_loss_threshold'], errors='coerce')
    normalized['stop_loss_triggered'] = normalized['stop_loss_triggered'].apply(lambda v: bool(v) if pd.notna(v) else False)
    normalized['stop_loss_message'] = normalized['stop_loss_message'].astype(object)
    normalized['stop_loss_ma_window'] = pd.to_numeric(normalized['stop_loss_ma_window'], errors='coerce')
    normalized['stop_loss_ticks'] = pd.to_numeric(normalized['stop_loss_ticks'], errors='coerce').fillna(0).astype(int)
    normalized['stop_loss_tick_size'] = pd.to_numeric(normalized['stop_loss_tick_size'], errors='coerce').fillna(0.01)

    # Type coercion for new numeric columns
    for col in ['return_5d', 'return_10d', 'return_14d', 'return_20d',
                 'max_return_14d', 'max_drawdown_14d', 'days_to_peak_14d',
                 'rs_value', 'rs_slope', 'ma20_slope', 'volume_expansion_ratio']:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors='coerce')
    for col in ['has_squeeze', 'has_houyi', 'has_whale', 'close_above_ma20',
                 'ma20_converging', 'volume_expansion', 'rs_new_high_60', 'hit_5pct_14d']:
        if col in normalized.columns:
            # Preserve NaN — only convert non-NA values to bool
            mask = normalized[col].notna()
            normalized[col] = normalized[col].astype(object)
            normalized.loc[mask, col] = normalized.loc[mask, col].astype(bool)
    for col in ['signal_score', 'ranking_score', 'experimental_score',
                'composite_score', 'composite_score_v2', 'rs_component_score']:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors='coerce')

    return normalized[TRACKING_COLUMNS]


# ---------------------------------------------------------------------------
# Helper: multi-window return calculation
# ---------------------------------------------------------------------------
def _compute_multi_window_returns(ticker_history: pd.DataFrame,
                                   entry_date: datetime) -> Dict[str, Any]:
    """
    Given the ticker's full price history and the entry date, calculate
    multiple forward return windows.

    Returns dict with keys: return_5d, return_10d, return_14d, return_20d,
    max_return_14d, max_drawdown_14d, hit_5pct_14d, days_to_peak_14d.
    """
    result = {
        'return_5d': None, 'return_10d': None,
        'return_14d': None, 'return_20d': None,
        'max_favorable_excursion_14d': None, 'max_adverse_excursion_14d': None,
        'hit_5pct_14d': False, 'days_to_peak_14d': None,
        'drawdown_before_hit_5pct': None,
        'hit_5pct_before_minus_5pct': False,
    }
    entry_date_naive = entry_date.replace(tzinfo=None) if entry_date.tzinfo else entry_date
    history = ticker_history.copy()
    if not isinstance(history.index, pd.DatetimeIndex):
        history.index = pd.to_datetime(history.index)
    # Find entry position
    entry_mask = history.index >= pd.Timestamp(entry_date_naive)
    if entry_mask.sum() == 0:
        return result

    entry_pos = entry_mask.argmax()  # first True position
    entry_close = float(history['Close'].iloc[entry_pos])

    if entry_close <= 0:
        return result

    future = history.iloc[entry_pos:]
    future_close = future['Close']

    windows = {5: 'return_5d', 10: 'return_10d', 14: 'return_14d', 20: 'return_20d'}
    for n_days, col in windows.items():
        # iloc[n_days] = price n trading days after entry
        if len(future_close) > n_days:
            result[col] = float((future_close.iloc[n_days] / entry_close - 1.0) * 100)

    # Max favorable/adverse excursion within 14 trading days of entry (days 0..14)
    if len(future_close) > 1:
        window_14 = future_close.iloc[:min(15, len(future_close))]  # 15 bars = entry + 14 trading days
        max_close = float(window_14.max())
        min_close = float(window_14.min())
        mfe = float((max_close / entry_close - 1.0) * 100)
        mae = float((min_close / entry_close - 1.0) * 100)
        result['max_favorable_excursion_14d'] = mfe
        result['max_adverse_excursion_14d'] = mae
        result['hit_5pct_14d'] = mfe >= 5.0
        # Days to peak
        peak_idx = window_14.idxmax()
        peak_pos = future_close.index.get_loc(peak_idx)
        result['days_to_peak_14d'] = int(peak_pos)
        # Drawdown before hitting 5% (if hit)
        if mfe >= 5.0:
            # Find first close >= 5% gain
            hit_idx = (future_close.iloc[:min(15, len(future_close))] / entry_close - 1.0) >= 0.05
            if hit_idx.any():
                hit_pos = hit_idx.argmax()
                min_before_hit = float(future_close.iloc[:hit_pos + 1].min())
                result['drawdown_before_hit_5pct'] = float((min_before_hit / entry_close - 1.0) * 100)
                result['hit_5pct_before_minus_5pct'] = mae >= -5.0

    return result


# ---------------------------------------------------------------------------
# PerformanceTracker
# ---------------------------------------------------------------------------
class PerformanceTracker:
    """Tracks Buy/Sell recommendations with full feature schema and multi-window returns."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_taiwan_now(self) -> datetime:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

    def _init_db(self):
        if not self.db_path.exists():
            df = pd.DataFrame(columns=TRACKING_COLUMNS)
            df.to_csv(self.db_path, index=False)

    def _load_db(self) -> pd.DataFrame:
        try:
            df = pd.read_csv(self.db_path)
        except Exception:
            self._init_db()
            df = pd.read_csv(self.db_path)
        return normalize_tracking_df(df)

    def _infer_market_context(self, benchmark_ticker: str = "^TWII") -> Dict[str, Any]:
        try:
            benchmark_data = download_market_data([benchmark_ticker], period="1y")
            if benchmark_data.empty:
                raise ValueError("empty benchmark data")

            if isinstance(benchmark_data.columns, pd.MultiIndex):
                benchmark_df = benchmark_data[benchmark_ticker].dropna(subset=['Close'])
            else:
                benchmark_df = benchmark_data.dropna(subset=['Close'])

            if benchmark_df.empty or len(benchmark_df) < 30:
                raise ValueError("insufficient benchmark data")

            closes = benchmark_df['Close']
            close_now = float(closes.iloc[-1])
            sma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else close_now
            sma200 = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else sma50
            return_20d = ((close_now / float(closes.iloc[-21])) - 1.0) * 100 if len(closes) >= 21 else 0.0

            if close_now > sma50 > sma200 and return_20d > 0:
                regime = "bull_trend"
            elif close_now < sma50 < sma200 and return_20d < 0:
                regime = "bear_trend"
            else:
                regime = "range_bound"

            return {
                "market_regime": regime,
                "benchmark_ticker": benchmark_ticker,
            }
        except Exception as exc:
            logger.warning(f"Unable to infer market regime from {benchmark_ticker}: {exc}")
            return {
                "market_regime": "unknown",
                "benchmark_ticker": benchmark_ticker,
            }

    def record_recommendations(
        self,
        results: List[Dict[str, Any]],
        rec_type: str = 'buy',
        market_context: Optional[Dict[str, Any]] = None,
        stop_loss_pct: Optional[float] = None,
        stop_loss_ma_window: Optional[int] = None,
        stop_loss_ticks: int = 0,
        stop_loss_tick_size: float = 0.01,
    ):
        """
        Records top 10 recommendations with full feature snapshot.
        Stores raw feature values at entry time — never re-computed.
        """
        if not results:
            return

        context = market_context.copy() if market_context else self._infer_market_context()

        # Sort and take top 10
        if rec_type == 'buy':
            sorted_results = sorted(results, key=lambda x: x.get('momentum', 0), reverse=True)[:10]
        else:
            sorted_results = sorted(results, key=lambda x: x.get('momentum', 0), reverse=False)[:10]

        now_str = self._get_taiwan_now().strftime("%Y-%m-%d")
        new_records = []

        for r in sorted_results:
            new_records.append({
                # identity
                'date': now_str,
                'ticker': r.get('ticker'),
                'name': r.get('name'),
                'entry_price': r.get('Close'),
                # signal
                'signal': r.get('Signal', '觀望'),
                'signal_score': r.get('signal_score', r.get('composite_score', 0)),
                # pattern booleans
                'has_squeeze': r.get('is_squeezed', r.get('squeeze_on', False)),
                'has_houyi': r.get('has_houyi', False),
                'has_whale': r.get('has_whale', False),
                # MA20
                'close_above_ma20': r.get('close_above_ma20', False),
                'ma20_slope': r.get('ma20_slope', 0.0),
                'ma20_converging': r.get('ma20_converging', False),
                # volume
                'volume_expansion': r.get('volume_expansion', False),
                'volume_expansion_ratio': r.get('volume_expansion_ratio', 1.0),
                # RS raw values
                'rs_ratio': r.get('rs_ratio'),
                'rs_slope_5d': r.get('rs_slope_5d', 0.0),
                'rs_new_high_60': r.get('rs_new_high_60', False),
                # scores
                'ranking_score': r.get('ranking_score', r.get('composite_score', np.nan)),
                'experimental_score': r.get('experimental_score', r.get('composite_score_v2', np.nan)),
                'rs_component_score': r.get('rs_component_score', 0),
                'ranking_score_version': r.get('ranking_score_version', r.get('score_version', np.nan)),
                'feature_schema_version': r.get('feature_schema_version', 'unknown'),
                'feature_schema_date': r.get('feature_schema_date', 'unknown'),
                'scan_id': r.get('scan_id', np.nan),
                'rank_position_v1': r.get('rank_position_v1', r.get('rank_position', np.nan)),
                'ranking_percentile_v1': r.get('ranking_percentile_v1', r.get('ranking_percentile', np.nan)),
                'rank_position_v2': r.get('rank_position_v2', np.nan),
                'ranking_percentile_v2': r.get('ranking_percentile_v2', np.nan),
                # return windows (fresh — populated on next daily update)
                'return_5d': None,
                'return_10d': None,
                'return_14d': None,
                'return_20d': None,
                'max_return_14d': None,
                'max_drawdown_14d': None,
                'hit_5pct_14d': False,
                'days_to_peak_14d': None,
                # tracking state
                'current_price': r.get('Close'),
                'return_pct': 0.0,
                'strategy_return_pct': 0.0,
                'days_tracked': 0,
                'last_updated': now_str,
                'status': 'tracking',
                'type': rec_type,
                'pattern': context.get('pattern', 'squeeze'),
                'momentum': r.get('momentum', 0.0),
                'prev_momentum': r.get('prev_momentum', 0.0),
                'energy_level': r.get('energy_level', 0),
                'squeeze_on': r.get('is_squeezed', r.get('squeeze_on', False)),
                'fired': r.get('fired', False),
                'market_regime': context.get('market_regime', 'unknown'),
                'benchmark_ticker': context.get('benchmark_ticker', '^TWII'),
                'benchmark_symbol': r.get('benchmark_symbol', '^TWII'),
                'benchmark_period': r.get('benchmark_period', '2y'),
                'benchmark_source': r.get('benchmark_source', 'yfinance'),
                'benchmark_last_date': r.get('benchmark_last_date', np.nan),
                'value_score': r.get('value_score'),
                # stop loss
                'stop_loss_rule': f'fixed_pct_{stop_loss_pct:.2f}' if stop_loss_pct is not None and rec_type == 'buy' else None,
                'stop_loss_threshold': stop_loss_pct if rec_type == 'buy' else None,
                'stop_loss_triggered': False,
                'stop_loss_message': None,
                'stop_loss_ma_window': stop_loss_ma_window if rec_type == 'buy' else None,
                'stop_loss_ticks': stop_loss_ticks if rec_type == 'buy' else 0,
                'stop_loss_tick_size': stop_loss_tick_size if rec_type == 'buy' else 0.01,
            })

        df_new = pd.DataFrame(new_records)
        df_old = self._load_db()
        if df_old.empty:
            df_combined = df_new.copy()
        else:
            df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined = df_combined.drop_duplicates(
            subset=['date', 'ticker', 'type', 'feature_schema_version'],
            keep='last',
        )
        df_combined['date_dt'] = pd.to_datetime(df_combined['date'], errors='coerce')
        active = df_combined[df_combined['status'] == 'tracking'].sort_values(
            by=['date_dt', 'ticker'],
            ascending=[False, True],
        )
        completed = df_combined[df_combined['status'] != 'tracking']
        active = active.head(25)
        df_combined = pd.concat([active, completed], ignore_index=True)
        df_combined = df_combined.sort_values(by=['date_dt', 'ticker'], ascending=[False, True]).drop(columns=['date_dt'])
        df_combined = normalize_tracking_df(df_combined)
        df_combined.to_csv(self.db_path, index=False)
        logger.info(f"Recorded {len(new_records)} {rec_type} signals (Active list limited to 25)")

    def update_daily_performance(self) -> List[Dict[str, Any]]:
        """
        Updates performance for all active tracking items.
        Calculates multi-window returns from price history.
        """
        df = self._load_db()
        if df.empty:
            return []

        active = df[df['status'] == 'tracking'].copy()
        if active.empty:
            return []

        now = self._get_taiwan_now()
        now_str = now.strftime("%Y-%m-%d")

        # Skip if already updated today
        active = active[active['last_updated'] != now_str]
        if active.empty:
            return []

        tickers = active['ticker'].unique().tolist()
        logger.info(f"Updating performance for {len(tickers)} active trackers...")

        history_data = download_market_data(tickers, period="1y")
        if history_data.empty:
            return []

        results = []
        for index, row in active.iterrows():
            ticker = row['ticker']
            try:
                if len(tickers) == 1:
                    ticker_history = history_data.dropna(subset=['Close']).copy()
                else:
                    if ticker not in history_data.columns.get_level_values(0):
                        continue
                    ticker_history = history_data[ticker].dropna(subset=['Close']).copy()

                if ticker_history.empty:
                    continue

                price_now = float(ticker_history['Close'].iloc[-1])
                entry_price = float(row['entry_price'])
                return_pct = ((price_now - entry_price) / entry_price) * 100
                strategy_return_pct = -return_pct if row.get('type') == 'sell' else return_pct

                rec_date_str = row['date']
                try:
                    rec_date = datetime.strptime(rec_date_str, "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8)))
                except (ValueError, TypeError):
                    rec_date = now
                days_passed = (now - rec_date).days

                # Write current performance
                df.at[index, 'current_price'] = price_now
                df.at[index, 'return_pct'] = return_pct
                df.at[index, 'strategy_return_pct'] = strategy_return_pct
                df.at[index, 'days_tracked'] = days_passed
                df.at[index, 'last_updated'] = now_str

                # Multi-window returns
                mw = _compute_multi_window_returns(ticker_history, rec_date)
                for k, v in mw.items():
                    if k in df.columns:
                        # Convert bool to int/float for NaN-compatible columns
                        val = float(v) if isinstance(v, (bool, np.bool_)) else v
                        if val is not None and not (isinstance(val, float) and np.isnan(val)):
                            df.at[index, k] = val

                # Stop loss check
                stop_loss_message = self._build_stop_loss_message(df.loc[index], ticker_history)
                df.at[index, 'stop_loss_triggered'] = bool(stop_loss_message)
                df.at[index, 'stop_loss_message'] = stop_loss_message

                if days_passed >= 14:
                    df.at[index, 'status'] = 'completed'

                results.append(df.loc[index].to_dict())
            except Exception as e:
                logger.error(f"Error updating {ticker}: {e}")

        df.to_csv(self.db_path, index=False)
        return results

    def get_active_tracking_list(self, rec_type: Optional[str] = None) -> List[Dict[str, Any]]:
        df = self._load_db()
        if df.empty:
            return []

        mask = df['status'] == 'tracking'
        if rec_type:
            if 'type' in df.columns:
                mask = mask & (df['type'] == rec_type)
            elif rec_type == 'buy':
                pass
            else:
                return []

        active = df[mask].sort_values(by='date', ascending=False).head(25)
        return active.to_dict('records')

    def _build_stop_loss_message(self, row: pd.Series, ticker_history: pd.DataFrame) -> Optional[str]:
        if row.get('type') != 'buy':
            return None

        price_now = float(ticker_history['Close'].iloc[-1])
        stop_loss_pct = row.get('stop_loss_threshold')
        entry_price = row.get('entry_price')
        messages: List[str] = []

        if pd.notna(stop_loss_pct) and pd.notna(entry_price):
            threshold_price = float(entry_price) * (1.0 - float(stop_loss_pct) / 100.0)
            if float(price_now) <= threshold_price:
                messages.append(f"已觸發固定停損 {float(stop_loss_pct):.2f}%")

        ma_window = row.get('stop_loss_ma_window')
        stop_loss_ticks = row.get('stop_loss_ticks')
        tick_size = row.get('stop_loss_tick_size')
        if pd.notna(ma_window) and int(ma_window) > 0 and len(ticker_history) >= int(ma_window):
            ma_value = float(ticker_history['Close'].rolling(int(ma_window)).mean().iloc[-1])
            threshold = ma_value - (float(stop_loss_ticks or 0) * float(tick_size or 0.01))
            if float(price_now) < threshold:
                messages.append(f"已觸發{int(ma_window)}日線下{int(stop_loss_ticks or 0)}檔")

        if messages:
            return " / ".join(messages)
        return None
