import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import logging
from squeeze.data.downloader import download_market_data

logger = logging.getLogger(__name__)

class PerformanceTracker:
    """
    Tracks Buy and Sell recommendations daily for 14 days.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_taiwan_now(self) -> datetime:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

    def _init_db(self):
        if not self.db_path.exists():
            df = pd.DataFrame(columns=[
                'date', 'ticker', 'name', 'entry_price', 'signal', 
                'current_price', 'return_pct', 'days_tracked', 'last_updated', 'status', 'type'
            ])
            df.to_csv(self.db_path, index=False)

    def record_recommendations(self, results: List[Dict[str, Any]], rec_type: str = 'buy'):
        """
        Records top 10 recommendations of a specific type.
        rec_type: 'buy' or 'sell'
        """
        if not results:
            return

        # Sort and take top 10
        if rec_type == 'buy':
            # Highest momentum first
            sorted_results = sorted(results, key=lambda x: x.get('momentum', 0), reverse=True)[:10]
        else:
            # Lowest momentum first (most negative)
            sorted_results = sorted(results, key=lambda x: x.get('momentum', 0), reverse=False)[:10]

        now_str = self._get_taiwan_now().strftime("%Y-%m-%d")
        new_records = []
        
        for r in sorted_results:
            new_records.append({
                'date': now_str,
                'ticker': r.get('ticker'),
                'name': r.get('name'),
                'entry_price': r.get('Close'),
                'signal': r.get('Signal'),
                'current_price': r.get('Close'),
                'return_pct': 0.0,
                'days_tracked': 0,
                'last_updated': now_str,
                'status': 'tracking',
                'type': rec_type
            })
        
        df_new = pd.DataFrame(new_records)
        try:
            df_old = pd.read_csv(self.db_path)
            # Migration: add 'type' column if it doesn't exist
            if 'type' not in df_old.columns:
                df_old['type'] = 'buy'
        except Exception:
            self._init_db()
            df_old = pd.read_csv(self.db_path)
            
        # Avoid duplicate entries for same day/ticker
        df_combined = pd.concat([df_old, df_new]).drop_duplicates(subset=['date', 'ticker'], keep='last')
        
        # Limit total tracking list to 25 items (keep most recent)
        # Sort by date descending so newest are at top
        df_combined['date_dt'] = pd.to_datetime(df_combined['date'])
        df_combined = df_combined.sort_values(by=['date_dt'], ascending=False).drop(columns=['date_dt'])
        
        # Keep only top 25 records overall
        df_combined = df_combined.head(25)
        
        df_combined.to_csv(self.db_path, index=False)
        logger.info(f"Recorded {len(new_records)} {rec_type} signals to {self.db_path} (Limited to 25 total)")

    def update_daily_performance(self) -> List[Dict[str, Any]]:
        """
        Updates performance for all active tracking items.
        """
        df = pd.read_csv(self.db_path)
        if df.empty:
            return []

        # Find entries still in 'tracking' status
        active = df[df['status'] == 'tracking'].copy()
        if active.empty:
            return []

        now = self._get_taiwan_now()
        now_str = now.strftime("%Y-%m-%d")
        
        # Don't update if already updated today
        active = active[active['last_updated'] != now_str]
        if active.empty:
            return []

        tickers = active['ticker'].unique().tolist()
        logger.info(f"Updating performance for {len(tickers)} active trackers...")
        
        current_data = download_market_data(tickers, period="1d")
        if current_data.empty:
            return []
        
        results = []
        for index, row in active.iterrows():
            ticker = row['ticker']
            try:
                if len(tickers) == 1:
                    price_now = current_data['Close'].iloc[-1]
                else:
                    if ticker in current_data.columns.get_level_values(0):
                        price_now = current_data[ticker]['Close'].iloc[-1]
                    else:
                        continue
                
                entry_price = float(row['entry_price'])
                # Return calculation is the same for both buy/sell initially, 
                # but user views positive return on 'sell' as good (price went down).
                # We'll stick to price change % here and handle display in template.
                return_pct = ((price_now - entry_price) / entry_price) * 100
                
                rec_date = datetime.strptime(row['date'], "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8)))
                days_passed = (now - rec_date).days
                
                df.at[index, 'current_price'] = price_now
                df.at[index, 'return_pct'] = return_pct
                df.at[index, 'days_tracked'] = days_passed
                df.at[index, 'last_updated'] = now_str
                
                if days_passed >= 14:
                    df.at[index, 'status'] = 'completed'
                
                results.append(df.loc[index].to_dict())
            except Exception as e:
                logger.error(f"Error updating {ticker}: {e}")

        df.to_csv(self.db_path, index=False)
        return results

    def get_active_tracking_list(self, rec_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns currently tracking recommendations filtered by type."""
        df = pd.read_csv(self.db_path)
        if df.empty:
            return []
        
        mask = df['status'] == 'tracking'
        if rec_type:
            # Handle legacy data without 'type' column
            if 'type' in df.columns:
                mask = mask & (df['type'] == rec_type)
            elif rec_type == 'buy':
                pass # all legacy is buy
            else:
                return []
                
        active = df[mask].sort_values(by='date', ascending=False)
        return active.to_dict('records')
