# Squeeze TW Screener v1.2.1

專為台灣股市設計的自動化標的篩選工具，採用 Squeeze Momentum 擠壓動能邏輯與進階形態識別技術。對外命名與美股版 `squeeze-us` 對齊，台股命令統一為 `squeeze-tw`。

## 核心功能
- **高效能掃描**：採用混合多執行緒 (I/O) 與多處理器 (CPU) 引擎，快速掃描全台股 (包含上市、上櫃、興櫃)。
- **進階形態識別**：支援 TTM Squeeze、后羿射日 (Houyi Shooting Sun) 及大鯨魚交易 (Whale Trading) 形態。
- **明確交易信號**：每檔個股皆提供明確的操作建議，如「強烈買入 (爆發)」、「觀察 (跌勢收斂)」或「觀望」。
- **專業 HTML 報表**：自動生成美觀的 HTML 表格 Email，並夾帶 Top 15 潛力標的的 K 線分析圖。
- **自動化通知**：整合 LINE Bot 與 Email (SMTP) 通知，支援多收件人設定。
- **績效追蹤**：每日自動追蹤推薦標的的表現，資料庫自動維持在最新的 25 檔以內。
- **策略檢視**：保留完成追蹤的歷史資料，並可用分析命令檢查各類訊號、持有天數與市場 regime 的表現差異。

## 快速開始

### 安裝
```bash
pip install ./squeeze
```

### 執行掃描
```bash
# 掃描目前的擠壓動能標的，並生成圖表與發送通知
squeeze-tw scan --export --plot --notify
```

### 分析單一個股
```bash
# 可直接輸入台股代碼
PYTHONPATH=src python3 -m squeeze.cli analyze --ticker 2330
```

## 🌐 Web App (Streamlit)

一鍵產生 K 線圖 + RS 強度 + Squeeze 指標：

[![Streamlit App](https://img.shields.io/badge/Streamlit-🚀_開啟_Web_App-e94560?style=for-the-badge)](https://squeeze-tw-chart.streamlit.app)

或在本地執行：
```bash
pip install streamlit
streamlit run streamlit_app.py
```

### Deploy 到 Streamlit Cloud
1. Push 此 repo 到 GitHub
2. 到 [share.streamlit.io](https://share.streamlit.io) 選擇此 repo
3. Entry point: `streamlit_app.py`
4. Python version: 3.12
5. Deploy 完成即可使用

### GitHub Pages
靜態介紹頁面位於 `docs/` 目錄，啟用 GitHub Pages：
1. Repo Settings → Pages
2. Source: Deploy from branch → `main` / `docs`

### 也相容完整 yfinance 代碼
```bash
PYTHONPATH=src python3 -m squeeze.cli analyze --ticker 2330.TW
```

### 繪製單一個股圖表
```bash
PYTHONPATH=src python3 -m squeeze.cli plot --ticker 2330

# 指定輸出路徑
PYTHONPATH=src python3 -m squeeze.cli plot --ticker 2330 --output exports/2330.png
```

### 檢視策略績效
```bash
python3 scripts/analyze_tracking.py --csv recommendations.csv
PYTHONPATH=src python3 -m squeeze.cli analyze-tracking --csv recommendations.csv
```
