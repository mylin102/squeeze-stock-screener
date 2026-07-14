#!/usr/bin/env python3
"""
Quick backtest runner for TW market.

Usage:
    python3 scripts/run_backtest.py --csv recommendations.csv [--output exports/tw_backtest_report.md]
"""

import sys
from pathlib import Path

# Add src to path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import argparse
from squeeze_backtest.engine import BacktestEngine
from squeeze_backtest.models import Market
from squeeze_backtest.strategies import get_market_specific_strategies
from squeeze_backtest.report import ReportGenerator


def main():
    parser = argparse.ArgumentParser(description="TW Market Backtest Runner")
    parser.add_argument(
        "--csv",
        default="recommendations.csv",
        help="路徑至追蹤 CSV (預設：recommendations.csv)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="輸出報告路徑"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="匯出 JSON 格式"
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=None,
        help="指定策略 (預設：所有台股專用策略)"
    )
    args = parser.parse_args()
    
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"\n[錯誤] CSV 文件不存在：{csv_path}")
        print(f"請先執行掃描：squeeze-tw scan --export")
        sys.exit(1)
    
    market = Market.TW
    
    print(f"\n{'='*70}")
    print(f"  Squeeze Backtest - TW Market (台灣股市)")
    print(f"{'='*70}\n")
    
    # Load data
    print(f"[1/4] 載入追蹤數據：{csv_path}")
    engine = BacktestEngine(market=market)
    df = engine.load_tracking_data(str(csv_path))
    
    if df.empty:
        print("[錯誤] 無法載入數據")
        sys.exit(1)
    
    completed = df[df['status'] == 'completed'] if 'status' in df.columns else df
    total = len(df)
    comp_count = len(completed)
    print(f"      總記錄：{total} | 已完成：{comp_count} | 追蹤中：{total - comp_count}\n")
    
    if comp_count == 0:
        print("[警告] 尚無已完成記錄，無法進行回測")
        print("       請等待追蹤數據累積至少 14 天")
        
        # 生成空報告
        from squeeze_backtest.models import StrategyComparison
        comparison = StrategyComparison(results=[])
        generator = ReportGenerator(output_dir=str(ROOT / "exports"))
        generator.generate_report(comparison, df, market, args.output)
        sys.exit(0)
    
    # Get strategies
    print("[2/4] 載入股專用策略...")
    if args.strategies:
        all_strats = get_market_specific_strategies("all")
        selected = {k: v for k, v in all_strats.items() if k in args.strategies}
        if not selected:
            print(f"[錯誤] 無效策略名稱，可用：{list(all_strats.keys())}")
            sys.exit(1)
        strategies = selected
    else:
        strategies = get_market_specific_strategies(market.value)
    
    print(f"      載入 {len(strategies)} 個策略:\n")
    for name in strategies.keys():
        print(f"        - {name}")
    print()
    
    # Run backtest
    print("[3/4] 執行回測分析...")
    comparison = engine.compare_strategies(df, strategies)
    
    # Display summary
    print("\n[4/4] 策略績效摘要:\n")
    print("-" * 70)
    results_df = comparison.to_dataframe()
    
    # Print with formatting
    for _, row in results_df.iterrows():
        marker = "🏆" if comparison.best_strategy and row['Strategy'] == comparison.best_strategy.strategy_name else "  "
        total_return = row['Total Return %']
        return_str = f"+{total_return:.2f}%" if total_return > 0 else f"{total_return:.2f}%"
        
        print(f"{marker} {row['Strategy']:<20} | 交易：{row['Trades']:>3} | "
              f"勝率：{row['Win Rate %']:>5.1f}% | 報酬：{return_str:>10}")
    
    print("-" * 70)
    
    # Generate report
    generator = ReportGenerator(output_dir=str(ROOT / "exports"))
    report_path = generator.generate_report(comparison, df, market, args.output)
    
    if args.json:
        json_path = generator.export_json(comparison)
        print(f"\n      JSON 報告：{json_path}")
    
    # Print best strategy
    if comparison.best_strategy:
        best = comparison.best_strategy
        print(f"\n{'='*70}")
        print(f"🏆 最佳策略：{best.strategy_name}")
        print(f"   總報酬：{best.total_return_pct:+.2f}%")
        print(f"   勝率：{best.win_rate_pct:.1f}%")
        print(f"   Sharpe 比率：{best.sharpe_ratio:.2f}")
        print(f"   最大回撤：{best.max_drawdown_pct:.2f}%")
        print(f"   盈虧比：{best.profit_factor:.2f}")
    
    print(f"\n{'='*70}")
    print(f"✓ 回測完成！報告已儲存至：{report_path}")
    print(f"{'='*70}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
