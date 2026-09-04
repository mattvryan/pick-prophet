"""Tests for M08 residual variant registries."""

from __future__ import annotations

from pick_prophet.features.matrix_schema import MODEL_FEATURE_COLUMNS
from pick_prophet.models.residual_variants import (
    COMBINED_COLUMNS,
    HISTORY_COLUMNS,
    MARKET_CONTEXT_COLUMNS,
    PROHIBITED_ADJUSTMENT_EXACT,
    SITE_TEMPORAL_COLUMNS,
    VARIANTS,
    assert_variants_valid,
)


def test_variants_subset_of_model_features() -> None:
    assert_variants_valid()
    for columns in VARIANTS.values():
        assert set(columns) <= set(MODEL_FEATURE_COLUMNS)


def test_market_only_empty() -> None:
    assert VARIANTS["market_only"] == ()


def test_no_moneylines_or_neutral_in_variants() -> None:
    for columns in VARIANTS.values():
        assert "home_moneyline" not in columns
        assert "away_moneyline" not in columns
        assert "neutral_site" not in columns
        assert "home_market_logit" not in columns


def test_combined_is_ordered_union() -> None:
    assert COMBINED_COLUMNS == tuple(
        dict.fromkeys(
            (*SITE_TEMPORAL_COLUMNS, *HISTORY_COLUMNS, *MARKET_CONTEXT_COLUMNS)
        )
    )


def test_prohibited_set_covers_baseline_proxies() -> None:
    assert "home_implied_prob" in PROHIBITED_ADJUSTMENT_EXACT
    assert "home_moneyline" in PROHIBITED_ADJUSTMENT_EXACT
