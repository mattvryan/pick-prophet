"""Tests for M07 matrix builder projection and exclusions."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pick_prophet.features.matrix import (
    build_and_write,
    build_matrix_from_rows,
    write_matrix_csv,
)
from pick_prophet.features.matrix_schema import MATRIX_COLUMNS, MODEL_FEATURE_COLUMNS


def _base_row(**overrides: object) -> dict:
    row = {
        "game_id": "1",
        "season": "2099",
        "week": "2",
        "season_type": "regular",
        "kickoff_utc": "2099-09-08T18:00:00+00:00",
        "home_team_id": "10",
        "away_team_id": "20",
        "home_team": "Home",
        "away_team": "Away",
        "home_win": "1",
        "home_implied_prob": "0.55",
        "home_market_logit": "0.2",
        "home_conference": "X",
        "away_conference": "Y",
        "home_classification": "fbs",
        "away_classification": "fbs",
        "neutral_site": "false",
        "spread_home": "-3.5",
        "total": "50",
        "home_moneyline": "-150",
        "away_moneyline": "130",
        "line_provider_count": "3",
        "spread_home_open": "",
        "total_open": "",
        "spread_move_home": "",
        "total_move": "",
        "source_snapshot": "snap",
        "market_timing": "cfbd_historical_closing_like_no_observation_timestamp",
        "post_kick_provider_quotes_rejected": "0",
        "moneyline_fabricated_from_spread": "false",
        "sampling_frame": "all_fbs",
        "verification_status": "",
        "match_status": "",
        "is_pickem_game": "",
        "espn_home_pick_pct": "",
        "espn_expert_home_pct": "",
        "elo_home": "1500",
        "elo_away": "1400",
        "fpi_home": "",
        "ap_home_rank": "5",
    }
    row.update({k: str(v) if v is not None else "" for k, v in overrides.items()})
    return row


def test_extra_elo_column_stripped_from_output(tmp_path: Path) -> None:
    result = build_matrix_from_rows([(2099, "snap", [_base_row()])])
    assert "elo_home" not in result.rows[0]
    assert set(result.rows[0]) == set(MATRIX_COLUMNS)
    path = tmp_path / "m.csv"
    write_matrix_csv(result.rows, path)
    with path.open() as handle:
        header = next(csv.reader(handle))
    assert header == list(MATRIX_COLUMNS)
    assert "elo_home" not in header


def test_adversarial_columns_cannot_enter_model_features() -> None:
    row = _base_row(
        **{
            "home_win_copy": "1",
            "public_share": "60",
            "random_numeric": "123",
        }
    )
    result = build_matrix_from_rows([(2099, "snap", [row])])
    projected = result.rows[0]
    for bad in ("home_win_copy", "public_share", "random_numeric", "elo_home"):
        assert bad not in projected
        assert bad not in MODEL_FEATURE_COLUMNS


def test_ordinary_missing_market_retains_row() -> None:
    row = _base_row(home_implied_prob="", home_market_logit="", spread_home="")
    result = build_matrix_from_rows([(2099, "snap", [row])])
    assert len(result.rows) == 1
    assert result.rows[0]["home_implied_prob"] is None
    assert len(result.exclusions) == 0


def test_structural_missing_kickoff_excluded_with_reason() -> None:
    row = _base_row(kickoff_utc="")
    result = build_matrix_from_rows([(2099, "snap", [row])])
    assert result.rows == []
    assert result.exclusions[0].reason_code == "missing_kickoff"
    assert result.input_rows == 1
    assert result.input_rows == len(result.rows) + len(result.exclusions)


def test_duplicate_game_id_raises() -> None:
    rows = [_base_row(game_id="1"), _base_row(game_id="1", week="3")]
    with pytest.raises(ValueError, match="duplicate game_id"):
        build_matrix_from_rows([(2099, "snap", rows)])


def test_header_equals_matrix_columns(tmp_path: Path) -> None:
    result = build_matrix_from_rows([(2099, "snap", [_base_row()])])
    out = tmp_path / "out"
    # write via build_and_write requires file inputs
    src = tmp_path / "games_2099.csv"
    with src.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_base_row().keys()))
        writer.writeheader()
        writer.writerow(_base_row())
    build_and_write(input_paths=[src], seasons=[2099], output_dir=out)
    with (out / "games_matrix_v1.csv").open() as handle:
        header = next(csv.reader(handle))
    assert header == list(MATRIX_COLUMNS)
    assert result.rows[0]["home_field_advantage"] == 1
    assert result.rows[0]["is_week_1"] is False
    assert result.rows[0]["is_weeks_1_3"] is True


def test_movement_null_when_open_missing() -> None:
    result = build_matrix_from_rows([(2099, "snap", [_base_row()])])
    assert result.rows[0]["spread_move_home"] is None
    assert result.rows[0]["total_move"] is None
