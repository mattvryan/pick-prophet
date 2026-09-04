"""Unit tests for M07 matrix role allowlists."""

from __future__ import annotations

import pytest

from pick_prophet.features.matrix_schema import (
    AUDIT_SLICE_COLUMNS,
    BASELINE_INPUT_COLUMNS,
    IDENTIFIER_COLUMNS,
    MATRIX_COLUMNS,
    MATRIX_SCHEMA_VERSION,
    MODEL_FEATURE_COLUMNS,
    TARGET_COLUMNS,
    assert_no_deferred_ratings,
    assert_roles_disjoint,
)


def test_version_and_header_order() -> None:
    assert MATRIX_SCHEMA_VERSION == "1.0.0"
    assert MATRIX_COLUMNS == (
        *IDENTIFIER_COLUMNS,
        *TARGET_COLUMNS,
        *BASELINE_INPUT_COLUMNS,
        *MODEL_FEATURE_COLUMNS,
        *AUDIT_SLICE_COLUMNS,
    )


def test_roles_disjoint() -> None:
    assert_roles_disjoint()


def test_no_ratings_in_any_role() -> None:
    assert_no_deferred_ratings(MATRIX_COLUMNS)


def test_m08_surfaces_exclude_audit_and_target() -> None:
    for col in (
        "home_win",
        "espn_home_pick_pct",
        "market_timing",
        "source_snapshot",
        "game_id",
        "home_team",
    ):
        assert col not in MODEL_FEATURE_COLUMNS
        assert col not in BASELINE_INPUT_COLUMNS
    assert BASELINE_INPUT_COLUMNS == ("home_implied_prob", "home_market_logit")


def test_forbidden_names_raise() -> None:
    with pytest.raises(ValueError, match="deferred rating"):
        assert_no_deferred_ratings(["spread_home", "elo_home"])
