"""Tests for M10 ablation variant registry."""

from __future__ import annotations

import pytest

from pick_prophet.models.residual_ablation_variants import (
    ANOMALOUS_SEASONS,
    FAMILIES,
    MIN_ESPN_N,
    assert_ablation_variants_valid,
    build_ablation_variants,
    eligible_single_features,
)
from pick_prophet.models.residual_preprocess import CATEGORICAL_COLUMNS
from pick_prophet.models.residual_variants import COMBINED_COLUMNS, HISTORY_COLUMNS


def test_family_membership_exact() -> None:
    variants = build_ablation_variants()
    for name, cols in FAMILIES.items():
        assert variants[f"family__{name}"] == cols


def test_single_features_are_source_columns_not_onehots() -> None:
    variants = build_ablation_variants()
    for col in CATEGORICAL_COLUMNS & set(eligible_single_features()):
        assert variants[f"single__{col}"] == (col,)
        # Encoded level names must not appear as variant IDs
        assert f"single__{col}=SEC" not in variants


def test_leave_family_out_construction() -> None:
    variants = build_ablation_variants()
    for name, cols in FAMILIES.items():
        lof = variants[f"lof__without_{name}"]
        assert set(lof) == set(COMBINED_COLUMNS) - set(cols)
        assert all(c not in cols for c in lof)


def test_no_prohibited_or_deferred() -> None:
    assert_ablation_variants_valid()
    variants = build_ablation_variants()
    flat = {c for cols in variants.values() for c in cols}
    assert "home_market_logit" not in flat
    assert "elo_home" not in flat
    assert "neutral_site" not in flat


def test_combined_and_market_only() -> None:
    variants = build_ablation_variants()
    assert variants["market_only"] == ()
    assert variants["combined"] == COMBINED_COLUMNS
    assert set(eligible_single_features()) == set(COMBINED_COLUMNS)


def test_constants() -> None:
    assert MIN_ESPN_N == 50
    assert ANOMALOUS_SEASONS == (2020,)


def test_invalid_single_rejected() -> None:
    bad = build_ablation_variants()
    bad["single__home_conference"] = ("home_conference", "away_conference")
    with pytest.raises(ValueError, match="must contain only source column"):
        assert_ablation_variants_valid(bad)


def test_history_family_present() -> None:
    assert build_ablation_variants()["family__history"] == HISTORY_COLUMNS
