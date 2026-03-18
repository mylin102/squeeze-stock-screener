import typer
import pandas as pd
from rich.console import Console
from rich.table import Table
from pathlib import Path

from typing import List, Optional, Dict, Any

from squeeze.data.tickers import fetch_tickers as do_fetch_tickers
from squeeze.data.downloader import download_market_data
from squeeze.engine.indicators import calculate_squeeze_indicators
from squeeze.engine.patterns import detect_squeeze, detect_houyi_shooting_sun, detect_whale_trading
from squeeze.engine.scanner import MarketScanner
from squeeze.report.exporter import ReportExporter
from squeeze.report.visualizer import plot_ticker

app = typer.Typer(help="Squeeze Stock Screener for Taiwan Market")
console = Console()

@app.command(name="scan")
def scan(
    pattern: str = typer.Option("squeeze", "--pattern", "-P", help="Pattern to scan for (squeeze, houyi, whale)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit the number of tickers to scan (for testing)"),
    period: str = typer.Option("2y", "--period", "-p", help="Data period (e.g., 2y, 1y, 6mo)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export results to CSV/JSON/MD"),
    plot: bool = typer.Option(False, "--plot", help="Generate charts for top picks"),
    top: int = typer.Option(10, "--top", help="Number of top picks to plot"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory for reports and charts")
):
    """
    Scan all Taiwan stocks for specific technical patterns.
    """
    console.print(f"[yellow]Scanning for {pattern} pattern...[/yellow]")
    
    # Map pattern names to functions and result filters
    pattern_map = {
        "squeeze": {
            "fn": detect_squeeze,
            "filter": lambda r: r.get('is_squeezed'),
            "title": "Squeeze Scan Results",
            "sort_key": lambda x: x.get('energy_level', 0)
        },
        "houyi": {
            "fn": detect_houyi_shooting_sun,
            "filter": lambda r: r.get('is_houyi'),
            "title": "Houyi Shooting the Sun Results",
            "sort_key": lambda x: x.get('rally_pct', 0)
        },
        "whale": {
            "fn": detect_whale_trading,
            "filter": lambda r: r.get('is_whale'),
            "title": "Whale Trading Alignment Results",
            "sort_key": lambda x: x.get('weekly_momentum', 0)
        }
    }
    
    if pattern not in pattern_map:
        console.print(f"[red]Unknown pattern: {pattern}. Available patterns: {list(pattern_map.keys())}[/red]")
        return

    config = pattern_map[pattern]
    
    console.print("[yellow]Discovering Taiwan market tickers...[/yellow]")
    all_tickers = do_fetch_tickers()
    
    if limit:
        all_tickers = all_tickers[:limit]
        console.print(f"[yellow]Limiting scan to {limit} tickers.[/yellow]")
    
    console.print(f"[green]Scanning {len(all_tickers)} tickers...[/green]")
    
    scanner = MarketScanner(all_tickers)
    
    with console.status("[bold green]Downloading market data...[/bold green]"):
        scanner.fetch_data(period=period)
        
    with console.status("[bold green]Analyzing patterns...[/bold green]"):
        results = scanner.scan(config['fn'])
    
    # Filter results for display
    matched = [r for r in results if config['filter'](r)]
    matched = sorted(matched, key=config['sort_key'], reverse=True)
    
    # Create the result table
    table = Table(title=f"{config['title']} ({len(matched)} matches)")
    table.add_column("Ticker", style="cyan")
    
    if pattern == "squeeze":
        table.add_column("Energy", style="yellow")
        table.add_column("Momentum", style="green")
        table.add_column("Fired", style="red")
        for r in matched:
            energy_stars = "★" * r.get('energy_level', 0)
            momentum_color = "green" if r.get('momentum', 0) > 0 else "red"
            table.add_row(
                r['ticker'],
                f"{r['energy_level']} {energy_stars}",
                f"[{momentum_color}]{r['momentum']:.4f}[/{momentum_color}]",
                "YES" if r.get('fired') else ""
            )
    elif pattern == "houyi":
        table.add_column("Rally %", style="yellow")
        table.add_column("Fib Level", style="magenta")
        table.add_column("Squeeze", style="blue")
        table.add_column("Star", style="red")
        for r in matched:
            table.add_row(
                r['ticker'],
                f"{r['rally_pct']*100:.1f}%",
                f"{r['fib_level']:.2f}",
                "YES" if r.get('squeeze_on') else "no",
                "YES" if r.get('shooting_star') else "no"
            )
    elif pattern == "whale":
        table.add_column("D-Sq", style="yellow")
        table.add_column("W-Sq", style="magenta")
        table.add_column("D-Mom", style="green")
        table.add_column("W-Mom", style="blue")
        for r in matched:
            d_mom_color = "green" if r.get('daily_momentum', 0) > 0 else "red"
            w_mom_color = "green" if r.get('weekly_momentum', 0) > 0 else "red"
            table.add_row(
                r['ticker'],
                "YES" if r.get('daily_squeeze') else "no",
                "YES" if r.get('weekly_squeeze') else "no",
                f"[{d_mom_color}]{r['daily_momentum']:.2f}[/{d_mom_color}]",
                f"[{w_mom_color}]{r['weekly_momentum']:.2f}[/{w_mom_color}]"
            )
    
    console.print(table)
    
    if not matched:
        console.print(f"[yellow]No stocks currently matched the {pattern} pattern.[/yellow]")
        return

    # Handle Exports and Plotting
    if export or plot:
        base_dir = output_dir or Path("exports")
        
        if export:
            console.print(f"[yellow]Exporting results to {base_dir}...[/yellow]")
            exporter = ReportExporter()
            paths = exporter.export(matched, base_dir)
            for fmt, path in paths.items():
                console.print(f"[green]Exported {fmt}: {path}[/green]")
        
        if plot:
            plot_count = min(len(matched), top)
            console.print(f"[yellow]Generating charts for top {plot_count} picks...[/yellow]")
            
            # Create charts subdirectory in the date folder
            date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
            charts_dir = base_dir / date_str / "charts"
            charts_dir.mkdir(parents=True, exist_ok=True)
            
            for i in range(plot_count):
                ticker = matched[i]['ticker']
                try:
                    # Extract ticker data from scanner's downloaded data
                    if len(all_tickers) == 1:
                        ticker_data = scanner.data
                    else:
                        ticker_data = scanner.data[ticker].dropna(subset=['Close'])
                    
                    chart_path = charts_dir / f"{ticker.split('.')[0]}.png"
                    plot_ticker(ticker_data, ticker, str(chart_path))
                    console.print(f"  [green]✔[/green] Generated chart for {ticker}")
                except Exception as e:
                    console.print(f"  [red]✘[/red] Error plotting {ticker}: {str(e)}")

@app.command(name="fetch-tickers")
def fetch_tickers():
    """
    Fetch TWSE/TPEx tickers and update the ticker database.
    """
    console.print("[yellow]Fetching tickers...[/yellow]")
    tickers = do_fetch_tickers()
    console.print(f"[green]Successfully discovered {len(tickers)} tickers![/green]")

@app.command(name="download")
def download(
    ticker: str = typer.Option(..., "--ticker", "-t", help="Ticker symbol (e.g., 2330.TW)"),
    period: str = typer.Option("1y", "--period", "-p", help="Data period (e.g., 1y, 6mo)")
):
    """
    Download historical data for a specific ticker.
    """
    console.print(f"[yellow]Downloading data for {ticker}...[/yellow]")
    df = download_market_data([ticker], period=period)
    
    if df.empty:
        console.print("[red]No data found.[/red]")
    else:
        console.print(f"[green]Downloaded {len(df)} rows.[/green]")
        console.print(f"Columns: {list(df.columns)}")

@app.command(name="analyze")
def analyze(
    ticker: str = typer.Option(..., "--ticker", "-t", help="Ticker symbol (e.g., 2330.TW)"),
    period: str = typer.Option("1y", "--period", "-p", help="Data period (e.g., 1y, 6mo)")
):
    """
    Download data and calculate Squeeze indicators for a specific ticker.
    """
    console.print(f"[yellow]Analyzing {ticker}...[/yellow]")
    df = download_market_data([ticker], period=period)
    
    if df.empty:
        console.print("[red]No data found.[/red]")
        return

    # If df is MultiIndex from bulk download, select the ticker
    if isinstance(df.columns, pd.MultiIndex):
        try:
            ticker_data = df[ticker].copy()
        except KeyError:
            console.print(f"[red]Ticker {ticker} not found in downloaded data.[/red]")
            return
    else:
        ticker_data = df.copy()

    try:
        results = calculate_squeeze_indicators(ticker_data)
        latest = results.iloc[-1]
        
        console.print(f"\n[bold underline]Latest Analysis for {ticker}[/bold underline]")
        
        status_color = "red" if latest['Squeeze_On'] else "green"
        status_text = "SQUEEZE ON" if latest['Squeeze_On'] else "NO SQUEEZE"
        console.print(f"Status: [{status_color}]{status_text}[/{status_color}]")
        
        if latest['Fired']:
            console.print("[bold cyan]*** SQUEEZE FIRED! ***[/bold cyan]")
            
        console.print(f"Energy Level: [bold]{latest['Energy_Level']}/3[/bold]")
        
        momentum_color = "green" if latest['Momentum'] > 0 else "red"
        console.print(f"Momentum: [{momentum_color}]{latest['Momentum']:.4f}[/{momentum_color}]")
        
        console.print(f"Close: {latest['Close']:.2f}")
        
    except Exception as e:
        console.print(f"[red]Error during calculation: {str(e)}[/red]")

if __name__ == "__main__":
    app()
