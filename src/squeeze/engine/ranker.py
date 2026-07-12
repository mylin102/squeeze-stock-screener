import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Current production ranking score version
RANKING_SCORE_VERSION = "v1"

# Feature schema version — bump when RS/Ratio/MA20/Volume fields change
# Format: phase<N><suffix> where suffix describes the major addition
FEATURE_SCHEMA_VERSION = "phase6a"
FEATURE_SCHEMA_DATE = "2026-07-12"

# ---------------------------------------------------------------------------
# Value Score (fundamental)
# ---------------------------------------------------------------------------

def calculate_value_score(df: pd.DataFrame) -> pd.DataFrame:
    """Percentile-based value score (0-1) from P/E, P/B, Dividend Yield."""
    if df.empty:
        return df
    res = df.copy()
    for col, asc in [("trailingPE", False), ("priceToBook", False), ("dividendYield", True)]:
        res[f"{col}_rank"] = res[col].rank(pct=True, ascending=asc) if col in res.columns else 0.5
    res["value_score"] = res[[f"{c}_rank" for c in ["trailingPE", "priceToBook", "dividendYield"]]].fillna(0.5).mean(axis=1)
    return res.drop(columns=[f"{c}_rank" for c in ["trailingPE", "priceToBook", "dividendYield"]])

# ---------------------------------------------------------------------------
# Signal scoring
# ---------------------------------------------------------------------------

def _signal_score(signal: str) -> int:
    if signal == "強烈買入 (爆發)":
        return 3
    if signal == "買入 (動能增強)":
        return 2
    if signal == "觀察 (跌勢收斂)":
        return 1
    return 0

# ---------------------------------------------------------------------------
# RS component score (0-3), three orthogonal dimensions
# ---------------------------------------------------------------------------

def _rs_component_score(result: Dict[str, Any]) -> int:
    """
    Compressed RS score across three independent dimensions (each 0-1):

    1. trend_structure: RS > EMA20 AND EMA20(RS) > EMA60(RS)
    2. momentum: RS_Slope_5d > 0 AND RS_Rising_10
    3. leadership: RS_New_High_60 OR RS_high_price_not_high

    Uses 5-day slope for momentum to avoid 1-day noise.
    Total range: 0-3
    """
    trend = int(
        result.get("rs_above_ema20", False)
        and result.get("rs_ema20_above_ema60", False)
    )
    momentum = int(
        result.get("rs_slope_5d", 0.0) > 0
        and result.get("rs_rising_10", False)
    )
    leadership = int(
        result.get("rs_new_high_60", False)
        or result.get("rs_high_price_not_high", False)
    )
    return trend + momentum + leadership

# ---------------------------------------------------------------------------
# Score versions
# ---------------------------------------------------------------------------

def calculate_score_v1(result: Dict[str, Any]) -> int:
    """
    Production score v1.
    Components: signal (0-3) + has_houyi (0-1) + has_whale (0-2)
    Range: 0-6
    """
    return (
        _signal_score(result.get("Signal", ""))
        + (1 if result.get("has_houyi", False) else 0)
        + (2 if result.get("has_whale", False) else 0)
    )


def calculate_shadow_ma20(result: Dict[str, Any]) -> int:
    """v1 + MA20 structure: close_above_ma20, ma20_slope>0. Range 0-8."""
    return (
        calculate_score_v1(result)
        + (1 if result.get("close_above_ma20", False) else 0)
        + (1 if result.get("ma20_slope", 0.0) > 0 else 0)
    )


def calculate_shadow_rs(result: Dict[str, Any]) -> int:
    """v1 + RS component. Range 0-9."""
    return calculate_score_v1(result) + _rs_component_score(result)


def calculate_score_v2(result: Dict[str, Any]) -> int:
    """
    Experimental score v2 — v1 + MA20 structure + RS.
    Range: 0-9 (same as shadow_rs for now — RS is the primary addition)
    """
    return calculate_shadow_rs(result)

# ---------------------------------------------------------------------------
# Enrichment pipeline
# ---------------------------------------------------------------------------

def enrich_with_scores(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich result dicts with all score fields and rank positions.

    Two independent rankings are computed:
      - rank_position_v1: v1 score only, tie-break = ticker ASC
        (completely uncontaminated by RS or experimental features)
      - rank_position_v2: experimental_score DESC → ranking_score DESC → ticker ASC

    This is the ONLY place scores are computed in the pipeline.

    Output fields:
      - ranking_score: v1 (production, 0-6)
      - experimental_score: v2 (v1 + RS, 0-9)
      - shadow_score_ma20 / shadow_score_rs: decomposition
      - rs_component_score: RS contribution only (0-3)
      - ranking_score_version: "v1"
      - feature_schema_version: "phase6a"
      - feature_schema_date: "2026-07-12"
      - rank_position_v1: v1 rank (1=best, ties broken by ticker ASC)
      - ranking_percentile_v1: 0-1 (1.0=best)
      - rank_position_v2: v2 rank (experimental_score DESC → ranking_score DESC)
      - ranking_percentile_v2: 0-1 (1.0=best)
    """
    enriched = []
    for r in results:
        row = dict(r)
        v1 = calculate_score_v1(r)
        row["ranking_score"] = v1
        row["ranking_score_version"] = RANKING_SCORE_VERSION
        row["feature_schema_version"] = FEATURE_SCHEMA_VERSION
        row["feature_schema_date"] = FEATURE_SCHEMA_DATE
        row["rs_component_score"] = _rs_component_score(r)
        row["experimental_score"] = calculate_score_v2(r)
        row["shadow_score_ma20"] = calculate_shadow_ma20(r)
        row["shadow_score_rs"] = calculate_shadow_rs(r)
        # Legacy compat
        row["composite_score"] = v1
        row["composite_score_v2"] = calculate_score_v2(r)
        row["score_version"] = RANKING_SCORE_VERSION
        enriched.append(row)

    n = len(enriched)
    # --- v1 ranking: pure ranking_score, tie-break = ticker ASC only ---
    ranked_v1 = sorted(
        enriched,
        key=lambda x: (-x.get("ranking_score", 0), x.get("ticker", "")),
    )
    for pos, item in enumerate(ranked_v1, start=1):
        item["rank_position_v1"] = pos
        item["ranking_percentile_v1"] = (n - pos) / max(n - 1, 1)
        # Legacy alias
        item["rank_position"] = pos
        item["ranking_percentile"] = (n - pos) / max(n - 1, 1)

    # --- v2 ranking: experimental_score → ranking_score → ticker ASC ---
    if n > 1:
        ranked_v2 = sorted(
            enriched,
            key=lambda x: (-x.get("experimental_score", 0), -x.get("ranking_score", 0), x.get("ticker", "")),
        )
        for pos, item in enumerate(ranked_v2, start=1):
            item["rank_position_v2"] = pos
            item["ranking_percentile_v2"] = (n - pos) / max(n - 1, 1)
    else:
        for item in enriched:
            item["rank_position_v2"] = 1
            item["ranking_percentile_v2"] = 1.0

    return enriched
