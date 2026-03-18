# Squeeze Stock Screener - User Guide (v1.0)

## Overview
The Squeeze Stock Screener is a professional-grade tool designed to identify high-potential trading entries in the Taiwan Stock Market. It combines John Carter's "Squeeze" logic with advanced pattern recognition and fundamental value analysis.

## Core Patterns

### 1. TTM Squeeze
Identifies periods of price consolidation (energy accumulation).
- **Squeeze ON**: Bollinger Bands are within Keltner Channels.
- **Squeeze OFF**: Bands have expanded, indicating a momentum breakout.

### 2. Houyi Shooting the Sun
A high-conviction momentum pattern.
- **Criteria**: >20% rally followed by a 50-61.8% Fibonacci retracement into a Squeeze, ending with a "Shooting Star" candlestick.

### 3. Whale Trading
Multi-timeframe institutional alignment.
- **Criteria**: Concurrent Squeezes on both **Daily** and **Weekly** charts with positive momentum.

## Fundamental Filtering
Filter the market for quality and value before applying technical analysis:
- `--min-mkt-cap`: Minimum market capitalization (in billion TWD).
- `--min-volume`: Minimum 20-day average volume.
- `--min-score`: Minimum **Value Score** (0.0 - 1.0).

### What is the Value Score?
A percentile-based ranking calculated across the entire Taiwan market:
- **Lower P/E**: Higher score.
- **Lower P/B**: Higher score.
- **Higher Dividend Yield**: Higher score.

## CLI Usage

### Basic Scan
```bash
squeeze scan --limit 100
```

### Advanced Scan with Filters and Charts
```bash
squeeze scan --pattern whale --min-mkt-cap 50 --min-score 0.7 --plot --export
```

## Automation
The project includes a pre-configured GitHub Actions workflow in `.github/workflows/daily_scan.yml`. It runs every weekday at 15:30 TST, saves reports to the `exports/` folder, and sends a summary to your LINE Bot.

---
*Disclaimer: This tool is for informational purposes only. Trading stocks involves high risk.*
