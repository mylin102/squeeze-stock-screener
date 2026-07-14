#!/usr/bin/env python3
"""
Squeeze TW Chart Viewer — Streamlit web app
Deploy on Streamlit Cloud (free): connect GitHub repo → app auto-deploys
"""
import sys
from pathlib import Path

# Ensure src/ is on path
_root = Path(__file__).parent
sys.path.insert(0, str(_root / "src"))

import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from squeeze.engine.scanner import MarketScanner
from squeeze.report.visualizer import plot_ticker
from squeeze.data.tickers import fetch_tickers_with_names
from squeeze.cli import _normalize_tw_ticker

st.set_page_config(page_title="Squeeze TW 個股圖表", page_icon="📈", layout="wide")

st.title("📈 Squeeze TW 個股技術圖表")
st.caption("輸入台股代號，自動產生 K 線圖 + RS 強度 + 技術指標")

# ── Sidebar ──
with st.sidebar:
    ticker = st.text_input("股票代號", value="2303", max_chars=6,
                           help="例如: 2303 (聯電), 2330 (台積電), 2317 (鴻海)")
    period = st.selectbox("資料期間", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=3)
    show_rs = st.checkbox("顯示 RS 強度", value=True)
    generate = st.button("🔥 產生圖表", type="primary", use_container_width=True)

# ── Main content ──
col1, col2 = st.columns([3, 1])

with col2:
    st.subheader("使用說明")
    st.markdown("""
    **支援的股票代號:**
    - 台股上市: `2330`, `2303`, `2317`
    - 上櫃: `6182`, `3105`, `8299`
    - 美股 (實驗): `AAPL`, `TSLA`

    圖表包含:
    - 📊 K 線圖 + 成交量
    - 🔴🟢 Squeeze 指標
    - 📈 RS (Relative Strength)
    - 🎯 技術分析摘要

    **Deploy:** 串接 GitHub → Streamlit Cloud 即可
    """)

if generate and ticker:
    ticker = ticker.strip()
    with st.spinner(f"下載 {ticker} 資料中..."):
        try:
            ticker_map = fetch_tickers_with_names()
            normalized = _normalize_tw_ticker(ticker, ticker_map)
            display_name = ticker_map.get(normalized, normalized)

            scanner = MarketScanner([normalized], ticker_names=ticker_map)
            scanner.fetch_data(period=period)

            if scanner.data.empty:
                st.error(f"❌ 無 {normalized} 的市場資料")
                st.stop()

            bm_close = None
            if show_rs:
                scanner.fetch_benchmark(period=period)
                bm_close = scanner.benchmark_close if not scanner.benchmark_close.empty else None

            if isinstance(scanner.data.columns, pd.MultiIndex):
                ticker_df = scanner.data[normalized].dropna(subset=["Close"])
            else:
                ticker_df = scanner.data.dropna(subset=["Close"])

            if ticker_df.empty:
                st.error(f"❌ 無 {normalized} 的圖表資料")
                st.stop()

        except Exception as e:
            st.error(f"❌ 資料取得失敗: {e}")
            st.stop()

    # Generate chart
    with st.spinner("繪製圖表中..."):
        try:
            fig, ax = plt.subplots(figsize=(14, 10))
            chart_path = f"/tmp/{normalized}_chart.png"

            plot_ticker(
                ticker_df=ticker_df,
                ticker_symbol=normalized,
                output_path=chart_path,
                benchmark_close=bm_close,
            )

            st.subheader(f"{normalized} ({display_name}) — {period}")
            st.image(chart_path, use_container_width=True)

            # Basic stats
            with col1:
                st.subheader("📊 技術摘要")
                last = ticker_df.iloc[-1]
                prev = ticker_df.iloc[-2] if len(ticker_df) > 1 else last
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("收盤價", f"{last['Close']:.2f}",
                          f"{last['Close'] - prev['Close']:+.2f}")
                c2.metric("最高", f"{last['High']:.2f}")
                c3.metric("最低", f"{last['Low']:.2f}")
                c4.metric("成交量", f"{int(last.get('Volume', 0)):,}")
                st.caption(f"資料期間: {ticker_df.index[0].date()} ~ {ticker_df.index[-1].date()}")

        except Exception as e:
            st.error(f"❌ 圖表產生失敗: {e}")
            import traceback
            st.code(traceback.format_exc())

else:
    with col1:
        st.info("👈 左側輸入股票代號，點擊「產生圖表」")
        # Show sample preview
        st.image("https://via.placeholder.com/800x400?text=Squeeze+TW+Chart+Preview",
                 use_container_width=True)
