# 基於追蹤報告的 Squeeze 策略回測框架 (TW Market)

## 概述

本文件定義如何根據 `recommendations.csv` 追蹤報告進行系統性回測，專為**台灣股市**設計。利用歷史推薦記錄驗證不同策略配置的實際表現。

---

## 一、台灣股市特性

### 1.1 市場結構

| 特性 | 台灣股市 (TW) | 中國 A 股 (CN) | 美國股市 (US) |
|------|--------------|--------------|--------------|
| 交易時間 | 9:00-13:30 TWT | 9:30-15:00 CST | 9:30-16:00 ET |
| 漲跌幅限制 | ±10% | ±10% (科創/創業±20%) | 無 (有熔斷) |
| 交易單位 | 1000 股 (1 張) | 100 股 (1 手) | 1 股 |
| 交割制度 | T+2 | T+1 | T+2 |
| 基準指數 | 0050.TW (TAIEX 50) | 000300.SS (CSI 300) | SPY (S&P 500) |

### 1.2 台股 Universe

預設掃描範圍：
- **上市股票** (~900 檔)
- **上櫃股票** (~800 檔)
- **興櫃股票** (~300 檔，可選)

主要指數成份股：
- **台灣 50** (0050.TW 成份股，大型權值)
- **中型 100** (0051.TW 成份股)
- **櫃買 50** (大型上櫃股)

---

## 二、台股專用策略配置

### 2.1 預設策略表

| 策略名稱 | 描述 | 關鍵參數 | 適用情境 |
|---------|------|---------|---------|
| `baseline` | 基準策略 | 無過濾器 | 所有市場 |
| `squeeze_only` | 純擠壓形態 | `require_squeeze_on=True`, `min_energy_level=2` | 盤整市場 |
| `whale_alignment` | 日週線共振 | `patterns=["whale"]`, `holding_days=10` | 趨勢明確 |
| `conservative` | 保守型 | `min_value_score=0.5`, `holding_days=14` | 穩健投資 |
| `scalping` | 短線當沖 | `holding_days=3`, `min_momentum=0.15` | 高波動 |
| `bull_market` | 多頭專用 | `allowed_regimes=["bull_trend"]` | 多頭 |
| `electronic` | 電子股專用 | `sector="電子"`, `holding_days=7` | 電子股 |
| `finance` | 金融股專用 | `sector="金融"`, `min_value_score=0.6` | 金融股 |

### 2.2 台股專用參數

```python
TW_SPECIFIC_PARAMS = {
    # 進場過濾器
    "min_price": 10.0,           # 最小股價 (TWD)
    "max_price": None,           # 最大股價
    "min_volume": 1000,          # 最小日均成交量 (張)
    "min_turnover": 10e6,        # 最小日均成交金額 (10M TWD)
    
    # 市場別過濾
    "market_type": None,         # None=全部，或 "上市", "上櫃", "興櫃"
    "exclude_emerging": True,    # 排除興櫃
    
    # 行業偏好
    "sectors": None,             # None=全部，或 ["電子", "金融", "傳產"]
    "exclude_sectors": [],       # 排除行業
    
    # 指數成份股偏好
    "tw50_only": False,          # 僅台灣 50
    "mid100_only": False,        # 僅中型 100
}
```

---

## 三、回測執行流程

### 3.1 數據準備

```python
import pandas as pd
from pathlib import Path

def load_tw_tracking_data(csv_path: str) -> pd.DataFrame:
    """載入台股追蹤數據"""
    df = pd.read_csv(csv_path)
    
    # 標準化欄位
    required_columns = [
        'date', 'ticker', 'name', 'entry_price', 'signal',
        'strategy_return_pct', 'days_tracked', 'status',
        'type', 'pattern', 'momentum', 'energy_level',
        'squeeze_on', 'fired', 'market_regime'
    ]
    
    for col in required_columns:
        if col not in df.columns:
            if col == 'strategy_return_pct':
                df[col] = df['return_pct'] if df['type'].iloc[0] == 'buy' else -df['return_pct']
            else:
                df[col] = None
    
    # 台股代碼標準化 (補上 .TW 或 .TWO)
    df['ticker'] = df['ticker'].apply(normalize_tw_ticker)
    
    return df

def normalize_tw_ticker(ticker: str) -> str:
    """標準化台股代碼"""
    ticker = ticker.strip().upper()
    
    # 如果已有後綴，直接返回
    if '.' in ticker:
        return ticker
    
    # 純數字，判斷是上市還是上櫃
    if ticker.isdigit():
        code = int(ticker)
        if code < 1000:  # 上市
            return f"{ticker}.TW"
        else:  # 上櫃
            return f"{ticker}.TWO"
    
    return ticker

def filter_completed(df: pd.DataFrame) -> pd.DataFrame:
    """只保留已完成追蹤的記錄"""
    return df[df["status"] == "completed"].copy()
```

### 3.2 台股專用回測引擎

```python
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class TWBacktestResult:
    strategy_name: str
    params: Dict
    total_trades: int
    win_rate: float
    avg_return: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    market_breakdown: Dict[str, float]  # 上市/上櫃分佈
    sector_breakdown: Dict[str, float]  # 行業分佈

def run_tw_backtest(
    df: pd.DataFrame,
    params: Dict,
    strategy_name: str = "custom"
) -> TWBacktestResult:
    """
    台股專用回測，包含市場別和行業分析
    """
    filtered = df.copy()
    
    # 1. 形態過濾
    if params.get("patterns"):
        filtered = filtered[filtered["pattern"].isin(params["patterns"])]
    
    # 2. 方向過濾
    if params.get("signal_types"):
        filtered = filtered[filtered["type"].isin(params["signal_types"])]
    
    # 3. 動能過濾
    if params.get("min_momentum") is not None:
        filtered = filtered[filtered["momentum"] >= params["min_momentum"]]
    if params.get("require_fired"):
        filtered = filtered[filtered["fired"] == True]
    
    # 4. 擠壓狀態過濾
    if params.get("require_squeeze_on"):
        filtered = filtered[filtered["squeeze_on"] == True]
    if params.get("min_energy_level") is not None:
        filtered = filtered[filtered["energy_level"] >= params["min_energy_level"]]
    
    # 5. 市場狀態過濾
    if params.get("allowed_regimes"):
        filtered = filtered[filtered["market_regime"].isin(params["allowed_regimes"])]
    
    # 6. 持有天數過濾
    holding_days = params.get("holding_days", 14)
    filtered = filtered[filtered["days_tracked"] <= holding_days]
    
    # 7. 價格過濾
    if params.get("min_price") is not None:
        filtered = filtered[filtered["entry_price"] >= params["min_price"]]
    
    # 8. 市場別過濾 (台股特色)
    if params.get("market_type"):
        # 假設有 market_type 欄位
        if "market_type" in filtered.columns:
            filtered = filtered[filtered["market_type"] == params["market_type"]]
    
    if params.get("exclude_emerging"):
        # 排除興櫃 (代碼 5 開頭或無 .TW/.TWO)
        filtered = filtered[~filtered["ticker"].str.startswith("5")]
    
    # 計算績效
    if filtered.empty:
        return TWBacktestResult(
            strategy_name=strategy_name,
            params=params,
            total_trades=0,
            win_rate=0.0,
            avg_return=0.0,
            total_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            profit_factor=0.0,
            market_breakdown={},
            sector_breakdown={}
        )
    
    returns = filtered["strategy_return_pct"]
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    
    total_trades = len(filtered)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    avg_return = returns.mean()
    total_return = returns.sum()
    
    # Sharpe Ratio
    daily_returns = filtered.groupby("date")["strategy_return_pct"].sum()
    sharpe_ratio = (daily_returns.mean() / daily_returns.std() * (252 ** 0.5)) if len(daily_returns) > 1 else 0
    
    # 最大回撤
    cumulative = (1 + daily_returns / 100).cumprod()
    rolling_max = cumulative.expanding().max()
    drawdowns = (cumulative / rolling_max) - 1
    max_drawdown = drawdowns.min() * 100
    
    # 盈虧比
    profit_factor = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float('inf')
    
    # 市場別分析 (上市/上櫃)
    market_breakdown = {}
    if "market_type" in filtered.columns:
        market_breakdown = filtered.groupby("market_type")["strategy_return_pct"].sum().to_dict()
    
    # 行業分析
    sector_breakdown = {}
    if "sector" in filtered.columns:
        sector_breakdown = filtered.groupby("sector")["strategy_return_pct"].sum().to_dict()
    
    return TWBacktestResult(
        strategy_name=strategy_name,
        params=params,
        total_trades=total_trades,
        win_rate=win_rate,
        avg_return=round(avg_return, 2),
        total_return=round(total_return, 2),
        sharpe_ratio=round(sharpe_ratio, 2),
        max_drawdown=round(max_drawdown, 2),
        profit_factor=round(profit_factor, 2) if profit_factor != float('inf') else 99.99,
        market_breakdown=market_breakdown,
        sector_breakdown=sector_breakdown
    )
```

### 3.3 批量回測

```python
def get_tw_strategies() -> Dict[str, Dict]:
    """返回台股專用策略配置"""
    return {
        "baseline": {
            "min_momentum": None,
            "require_squeeze_on": False,
            "require_fired": False,
            "patterns": ["squeeze", "houyi", "whale"],
            "signal_types": ["buy"],
            "holding_days": 14,
            "allowed_regimes": None,
        },
        "squeeze_only": {
            "require_squeeze_on": True,
            "min_energy_level": 2,
            "patterns": ["squeeze"],
            "signal_types": ["buy"],
            "holding_days": 14,
        },
        "whale_alignment": {
            "patterns": ["whale"],
            "signal_types": ["buy"],
            "holding_days": 10,
        },
        "conservative": {
            "min_value_score": 0.5,
            "patterns": ["squeeze", "whale"],
            "signal_types": ["buy"],
            "holding_days": 14,
        },
        "scalping": {
            "min_momentum": 0.15,
            "require_fired": True,
            "patterns": ["squeeze"],
            "signal_types": ["buy"],
            "holding_days": 3,
        },
        "bull_market": {
            "allowed_regimes": ["bull_trend"],
            "patterns": ["squeeze", "houyi", "whale"],
            "signal_types": ["buy"],
            "holding_days": 14,
        },
    }

def compare_tw_strategies(df: pd.DataFrame) -> pd.DataFrame:
    """比較所有台股策略的表現"""
    strategies = get_tw_strategies()
    
    results = []
    for name, params in strategies.items():
        result = run_tw_backtest(df, params, name)
        results.append(result)
    
    records = [
        {
            "Strategy": r.strategy_name,
            "Trades": r.total_trades,
            "Win Rate %": r.win_rate,
            "Avg Return %": r.avg_return,
            "Total Return %": r.total_return,
            "Sharpe": r.sharpe_ratio,
            "Max DD %": r.max_drawdown,
            "Profit Factor": r.profit_factor,
        }
        for r in results
    ]
    
    return pd.DataFrame(records).sort_values("Total Return %", ascending=False)
```

---

## 四、台股專用分析維度

### 4.1 市場別分析 (上市/上櫃/興櫃)

```python
def analyze_by_market_type(df: pd.DataFrame) -> pd.DataFrame:
    """分析不同市場別表現"""
    completed = df[df["status"] == "completed"]
    
    def infer_market_type(ticker: str) -> str:
        """從代碼推斷市場別"""
        if ".TW" in ticker:
            code = ticker.replace(".TW", "")
            if code.isdigit() and int(code) < 1000:
                return "上市"
            return "上櫃"
        elif ".TWO" in ticker:
            return "上櫃"
        elif ticker.startswith("5"):
            return "興櫃"
        return "未知"
    
    completed = completed.copy()
    completed["market_type"] = completed["ticker"].apply(infer_market_type)
    
    stats = completed.groupby("market_type").agg(
        trades=("ticker", "count"),
        win_rate=("strategy_return_pct", lambda x: (x > 0).mean() * 100),
        avg_return=("strategy_return_pct", "mean"),
        total_return=("strategy_return_pct", "sum")
    ).reset_index().sort_values("total_return", ascending=False)
    
    return stats
```

### 4.2 行業分析

```python
def analyze_tw_by_sector(df: pd.DataFrame) -> pd.DataFrame:
    """分析台股各行業表現"""
    if "sector" not in df.columns:
        # 嘗試從外部數據獲取行業
        df = add_tw_sector_data(df)
    
    if "sector" not in df.columns:
        return pd.DataFrame()
    
    completed = df[df["status"] == "completed"]
    
    # 台股主要行業分類
    sector_mapping = {
        "半導體": "Semiconductor",
        "電子零組件": "Electronics Components",
        "電腦及週邊": "Computer & Peripherals",
        "通訊網路": "Communication & Internet",
        "光電": "Optoelectronics",
        "金融保險": "Finance & Insurance",
        "證券": "Securities",
        "保險": "Insurance",
        "銀行": "Banking",
        "塑膠": "Plastics",
        "紡織": "Textiles",
        "食品": "Food",
        # ... 更多行業
    }
    
    stats = completed.groupby("sector").agg(
        trades=("ticker", "count"),
        win_rate=("strategy_return_pct", lambda x: (x > 0).mean() * 100),
        avg_return=("strategy_return_pct", "mean"),
        total_return=("strategy_return_pct", "sum")
    ).reset_index().sort_values("total_return", ascending=False)
    
    return stats

def add_tw_sector_data(df: pd.DataFrame) -> pd.DataFrame:
    """添加台股行業數據 (需要外部數據源)"""
    # 這裡可以連接外部 API 或本地數據庫
    # 例如：https://www.twse.com.tw/ 或 第三方數據源
    
    # 範例：本地快取
    sector_cache = {
        "2330.TW": "半導體",
        "2317.TW": "半導體",
        "2454.TW": "半導體",
        "2303.TW": "半導體",
        "2312.TW": "電子零組件",
        "2301.TW": "光電",
        "2357.TW": "通訊網路",
        "2353.TW": "電腦及週邊",
        "2881.TW": "金融保險",
        "2882.TW": "金融保險",
        "2883.TW": "金融保險",
        "2884.TW": "金融保險",
        "2885.TW": "金融保險",
        "2886.TW": "金融保險",
        "2891.TW": "證券",
        "2892.TW": "證券",
        # ... 更多股票
    }
    
    df = df.copy()
    df["sector"] = df["ticker"].map(sector_cache)
    
    return df
```

### 4.3 指數成份股分析

```python
def analyze_by_tw_index(df: pd.DataFrame) -> Dict[str, float]:
    """分析指數成份股表現"""
    completed = df[df["status"] == "completed"]
    
    # 定義指數成份股 (需要外部數據)
    tw50_tickers = {...}  # 台灣 50 成份股
    mid100_tickers = {...}  # 中型 100 成份股
    
    results = {}
    
    # 台灣 50
    tw50 = completed[completed["ticker"].isin(tw50_tickers)]
    if len(tw50) > 0:
        results["TW50"] = tw50["strategy_return_pct"].mean()
    
    # 中型 100
    mid100 = completed[completed["ticker"].isin(mid100_tickers)]
    if len(mid100) > 0:
        results["MID100"] = mid100["strategy_return_pct"].mean()
    
    # Others
    others = completed[~completed["ticker"].isin(tw50_tickers + mid100_tickers)]
    if len(others) > 0:
        results["Others"] = others["strategy_return_pct"].mean()
    
    return results
```

### 4.4 外資/投信/自營商分析

```python
def analyze_by_investor_type(df: pd.DataFrame) -> pd.DataFrame:
    """分析不同法人買賣超影響"""
    # 需要額外的法人買賣超數據
    # 可從 TWSE 或第三方數據源獲取
    
    if "foreign_investor_buy" not in df.columns:
        return pd.DataFrame()
    
    completed = df[df["status"] == "completed"]
    
    def investor_sentiment(row: pd.Series) -> str:
        """判斷法人情緒"""
        foreign = row.get("foreign_investor_buy", 0)
        dealer = row.get("dealer_buy", 0)
        
        if foreign > 0 and dealer > 0:
            return "全買"
        elif foreign > 0:
            return "外資買"
        elif dealer > 0:
            return "投信買"
        elif foreign < 0 and dealer < 0:
            return "全賣"
        else:
            return "中性"
    
    completed = completed.copy()
    completed["investor_sentiment"] = completed.apply(investor_sentiment, axis=1)
    
    stats = completed.groupby("investor_sentiment").agg(
        trades=("ticker", "count"),
        win_rate=("strategy_return_pct", lambda x: (x > 0).mean() * 100),
        avg_return=("strategy_return_pct", "mean")
    ).reset_index()
    
    return stats
```

---

## 五、執行命令

### 5.1 基本回測

```bash
cd /Users/mylin/Documents/mylin102/squeeze-tw-screener

# 使用通用回測框架
squeeze-backtest run -c recommendations.csv -m tw

# 或使用快速腳本
PYTHONPATH=../squeeze-backtest/src python3 ../squeeze-backtest/scripts/quick_backtest.py \
    --csv recommendations.csv \
    --market tw
```

### 5.2 指定策略

```bash
# 只執行特定策略
squeeze-backtest run -c recommendations.csv -m tw \
    -s squeeze_only \
    -s whale_alignment \
    -s conservative

# 輸出 JSON
squeeze-backtest run -c recommendations.csv -m tw --json
```

---

## 六、台股注意事項

### 6.1 除權息季節

台股除權息季節約在 6-9 月：

```python
def adjust_for_dividend(df: pd.DataFrame, dividend_dates: Dict[str, str]) -> pd.DataFrame:
    """調整除權息影響"""
    filtered = df.copy()
    
    for idx, row in filtered.iterrows():
        ticker = row["ticker"]
        trade_date = pd.to_datetime(row["date"])
        
        if ticker in dividend_dates:
            ex_dividend_date = pd.to_datetime(dividend_dates[ticker])
            days_diff = (ex_dividend_date - trade_date).days
            
            # 除權息前 30 天到除權息日的交易需特別處理
            if 0 <= days_diff <= 30:
                # 可以選擇排除或調整報酬計算
                filtered = filtered.drop(idx)
    
    return filtered
```

### 6.2 融資融券

台股有融資融券制度：

- **融資**: 保證金成數通常 50%
- **融券**: 融券成數通常 40%
- **資增/券增**: 可能影響股價走勢

```python
def analyze_margin_trading(df: pd.DataFrame) -> pd.DataFrame:
    """分析融資融券變化"""
    if "margin_change" not in df.columns:
        return pd.DataFrame()
    
    completed = df[df["status"] == "completed"]
    
    def margin_sentiment(change: float) -> str:
        if change > 100:
            return "資增>100"
        elif change > 0:
            return "資增"
        elif change < -100:
            return "資減>100"
        else:
            return "資減"
    
    completed = completed.copy()
    completed["margin_sentiment"] = completed["margin_change"].apply(margin_sentiment)
    
    stats = completed.groupby("margin_sentiment").agg(
        trades=("ticker", "count"),
        win_rate=("strategy_return_pct", lambda x: (x > 0).mean() * 100),
        avg_return=("strategy_return_pct", "mean")
    ).reset_index()
    
    return stats
```

### 6.3 漲停/跌停限制

台股有 ±10% 漲跌停限制，可能影響進出場：

```python
def check_price_limit(df: pd.DataFrame) -> pd.DataFrame:
    """檢查漲跌停影響"""
    completed = df[df["status"] == "completed"]
    
    # 假設有 high_limit 和 low_limit 欄位
    completed = completed.copy()
    completed["hit_limit"] = False
    
    for idx, row in completed.iterrows():
        entry_price = row["entry_price"]
        current_price = row["current_price"]
        return_pct = row["return_pct"]
        
        # 接近漲跌停
        if abs(return_pct) >= 9.5:  # 接近 10%
            completed.at[idx, "hit_limit"] = True
    
    limit_stats = completed.groupby("hit_limit").agg(
        trades=("ticker", "count"),
        avg_return=("strategy_return_pct", "mean")
    ).reset_index()
    
    return limit_stats
```

---

## 七、策略調整建議生成

```python
def generate_tw_recommendations(
    results_df: pd.DataFrame,
    completed: pd.DataFrame,
    market_analysis: pd.DataFrame = None,
    sector_analysis: pd.DataFrame = None
) -> List[str]:
    """生成台股專用建議"""
    recs = []
    
    if len(results_df) == 0:
        return ["數據不足，無法生成建議"]
    
    best = results_df.iloc[0]
    
    # 檢查短線策略
    scalping = results_df[results_df["Strategy"] == "scalping"]
    if len(scalping) > 0 and scalping.iloc[0]["Total Return %"] > 10:
        recs.append("短線當沖策略表現優異，適合台股高波動特性")
    
    # 檢查行業集中度
    if sector_analysis is not None and len(sector_analysis) > 0:
        top_sector = sector_analysis.iloc[0]
        if top_sector["total_return"] > 15:
            recs.append(f"行業 '{top_sector['sector']}' 表現優異，可考慮增加配置")
    
    # 檢查市場別
    if market_analysis is not None and len(market_analysis) > 0:
        if "上市" in market_analysis["market_type"].values:
            listed_return = market_analysis[market_analysis["market_type"] == "上市"]["total_return"].iloc[0]
            if listed_return > market_analysis[market_analysis["market_type"] == "上櫃"]["total_return"].iloc[0]:
                recs.append("上市股票表現優於上櫃，建議聚焦大型權值股")
    
    # 檢查最大回撤
    if best["Max DD %"] < -20:
        recs.append(f"最大回撤 {best['Max DD %']:.2f}% 過大，建議加入停損或減少倉位")
    
    # 檢查持有天數
    holding_analysis = completed.groupby("days_tracked")["strategy_return_pct"].mean()
    if len(holding_analysis) > 3:
        best_day = holding_analysis.idxmax()
        if best_day <= 5:
            recs.append(f"短天期 (第{best_day}天) 報酬最佳，適合台股短線操作")
        elif best_day >= 10:
            recs.append(f"長天期 (第{best_day}天) 報酬最佳，適合波段操作")
    
    if not recs:
        recs.append("目前策略表現良好，持續追蹤並累積更多數據")
    
    return recs
```

---

## 八、範例報告結構

```markdown
# Squeeze 台股策略回測報告

**市場**: 台灣股市 (TW)
**基準指數**: 0050.TW (TAIEX 50)
**報告日期**: 2026-03-28
**數據範圍**: 2026-01-01 至 2026-03-28

## 策略比較
[策略比較表格]

## 最佳策略分析
[詳細分析]

## 市場別分析
| 市場 | 交易數 | 勝率 | 平均報酬 | 總報酬 |
|-----|-------|------|---------|-------|
| 上市 | 50 | 55% | 2.5% | 125% |
| 上櫃 | 30 | 45% | 1.2% | 36% |

## 行業分析
[各行業表現]

## 指數比較
- 策略報酬：XX%
- 0050.TW 報酬：XX%
- 超額報酬：XX%

## 策略建議
[自動生成建議]
```

---

## 九、台股數據來源

### 9.1 官方數據源

- **TWSE 台灣證券交易所**: https://www.twse.com.tw/
- **TPEx 櫃檯買賣中心**: https://www.tpex.org.tw/

### 9.2 第三方 API

- **yfinance**: 支援台股 (代碼需加 .TW 或 .TWO)
- **twstock**: 台股專用 Python 套件
- **FinLab TW**: 台灣財經數據實驗室

### 9.3 法人數據

- **TWSE 三大法人**: https://www.twse.com.tw/zh/page/trading/fund/MIQFIN.html

---

*文件版本：v1.0 (TW Market)*
*建立日期：2026-03-28*
*適用專案：squeeze-tw-screener v1.2.1+*
