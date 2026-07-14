# RS (Relative Strength) — 相對強勢指標

## Overview

RS 衡量**個股相對大盤的強度**。不同於 Squeeze、MA20、型態等價格絕對值指標，RS 回答的是：

> 這檔股票是否持續跑贏大盤？

## 定義

### RS_Ratio（計算用）

```
RS_Ratio = Close_stock / Close_benchmark
```

- 個股每日收盤價 ÷ 加權指數收盤價（^TWII）
- EMA、斜率、新高、百分位等特徵使用此數值計算
- 跨下載期間穩定，不受資料區間長短影響

### RS_Index（圖表用）

```
RS_Index = 100 × RS_Ratio / RS_Ratio[0]
```

- 基期歸一化為 100，便於圖表閱讀
- 100 = 與大盤同步；110 = 跑贏 10%；90 = 跑輸 10%
- 圖表使用此數值，底層特徵計算仍使用 RS_Ratio

## 圖表說明

RS panel 為圖中最下方第四個面板（從上而下：K線、Momentum、Squeeze、RS Index）。

| 線 | 顏色 | 意義 |
|---|---|---|
| RS Index | 紫色 | 個股 ÷ 大盤，基期 100 |
| EMA20 | 紅色 (alpha 0.7) | RS 的 20 日 EMA（短線趨勢） |
| EMA60 | 藍色 (alpha 0.5) | RS 的 60 日 EMA（中長線趨勢） |

## 衍生特徵

所有特徵使用 RS_Ratio 計算，跨股票可比較。

### 趨勢結構 (trend)

| 特徵 | 條件 |
|---|---|
| `RS_Above_EMA20` | RS_Ratio > EMA20(RS_Ratio) |
| `RS_Above_EMA60` | RS_Ratio > EMA60(RS_Ratio) |
| `RS_EMA20_Above_EMA60` | EMA20(RS) > EMA60(RS) |

EMA60 上彎代表中長線相對強勢。

### 動能 (momentum)

| 特徵 | 說明 |
|---|---|
| `RS_Slope_1d` | EMA20 單日百分比變化 (%) |
| `RS_Slope_5d` | EMA20 5 日百分比變化 (%) — **主要動能指標** |
| `RS_Slope_20d` | EMA20 20 日百分比變化 (%) — 趨勢動能 |
| `RS_Rising_10` | RS 高於 10 個交易日前的數值 |

Slope 使用 `pct_change`（百分比變化）而非 `diff`（差值），確保不同股票的 slope 可比較。

### 領先性 (leadership)

| 特徵 | 條件 |
|---|---|
| `RS_New_High_60` | RS_Ratio 創 60 日新高（不含當日） |
| `RS_New_High_120` | RS_Ratio 創 120 日新高（不含當日） |
| `RS_High_Price_Not_High` | RS 創 60 日新高，但股價距 60 日高點 >10% |
| `RS_Percentile_60` | RS 在 60 日內的百分位 (0–1) |

`RS_New_High` 使用 `shift(1)` 排除當日，避免「與自己比較」的循環問題。

## RS Score 結構

RS 在 experimental score 中貢獻 **0–3 分**，壓縮為三個正交維度：

| 維度 | 條件 | 分數 |
|---|---|---|
| Trend | RS > EMA20 AND EMA20 > EMA60 | 0–1 |
| Momentum | RS_Slope_5d > 0 AND RS_Rising_10 | 0–1 |
| Leadership | RS_New_High_60 OR RS_High_Price_Not_High | 0–1 |

三個維度設計為**低相關性**，避免同一個趨勢被重複加分。

## 注意事項

- RS 為**相對指標**，不代表股價本身會漲
- RS 上升但股價下跌：股票跌幅小於大盤，可能為相對強勢
- RS 在 production score（ranking_score）中完全無影響 — 僅存在 experimental score
- benchmark 缺失時所有 RS 特徵為 NA，不會被誤判為弱勢
- 建議累積足夠樣本後再決定 RS 是否進入 production ranking
