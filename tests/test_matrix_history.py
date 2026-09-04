"""Tests for M07 chronological history and rest."""

from __future__ import annotations

import copy

import pytest

from pick_prophet.features.matrix_history import (
    NonPositiveRestError,
    attach_matrix_history,
)


def _game(
    game_id: int,
    *,
    season: int = 2099,
    week: int = 1,
    season_type: str = "regular",
    kickoff: str,
    home_id: int,
    away_id: int,
    home_win: int | None,
    home: str | None = None,
    away: str | None = None,
) -> dict:
    return {
        "game_id": game_id,
        "season": season,
        "week": week,
        "season_type": season_type,
        "kickoff_utc": kickoff,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team": home or f"H{home_id}",
        "away_team": away or f"A{away_id}",
        "home_win": home_win,
        # stale values that must be overwritten
        "home_entering_wins": 99,
        "home_days_rest": 99,
    }


def test_ignores_stale_history_columns_on_input() -> None:
    rows = [
        _game(1, kickoff="2099-09-01T18:00:00+00:00", home_id=1, away_id=2, home_win=1),
        _game(
            2,
            week=2,
            kickoff="2099-09-08T18:00:00+00:00",
            home_id=1,
            away_id=3,
            home_win=0,
        ),
    ]
    attach_matrix_history(rows)
    assert rows[0]["home_entering_wins"] == 0
    assert rows[0]["home_days_rest"] is None
    assert rows[1]["home_entering_wins"] == 1
    assert rows[1]["home_days_rest"] == 7


def test_rest_null_without_prior_completed_game() -> None:
    rows = [
        _game(1, kickoff="2099-09-01T18:00:00+00:00", home_id=1, away_id=2, home_win=None),
        _game(
            2,
            week=2,
            kickoff="2099-09-08T18:00:00+00:00",
            home_id=1,
            away_id=3,
            home_win=1,
        ),
    ]
    attach_matrix_history(rows)
    assert rows[0]["home_days_rest"] is None
    assert rows[1]["home_days_rest"] is None  # prior incomplete does not set rest


def test_rest_floor_day_delta() -> None:
    rows = [
        _game(1, kickoff="2099-09-01T18:00:00+00:00", home_id=1, away_id=2, home_win=1),
        _game(
            2,
            week=2,
            kickoff="2099-09-03T06:00:00+00:00",
            home_id=1,
            away_id=3,
            home_win=1,
        ),
    ]
    attach_matrix_history(rows)
    # 36 hours -> floor = 1 day
    assert rows[1]["home_days_rest"] == 1


def test_rest_rejects_non_positive() -> None:
    rows = [
        _game(1, kickoff="2099-09-08T18:00:00+00:00", home_id=1, away_id=2, home_win=1),
        _game(
            2,
            week=2,
            kickoff="2099-09-01T18:00:00+00:00",
            home_id=1,
            away_id=3,
            home_win=1,
        ),
    ]
    # Sorted by kickoff: game 2 first, then game 1 — fine.
    # Force same team with later game_id but earlier? Better: same kickoff order
    # with identical timestamps for completed then next with same timestamp.
    rows = [
        _game(1, kickoff="2099-09-01T18:00:00+00:00", home_id=1, away_id=2, home_win=1),
        _game(
            2,
            week=2,
            kickoff="2099-09-01T18:00:00+00:00",
            home_id=1,
            away_id=3,
            home_win=1,
        ),
    ]
    with pytest.raises(NonPositiveRestError):
        attach_matrix_history(rows)


def test_future_result_mutation_does_not_change_earlier_rest_or_record() -> None:
    rows = [
        _game(1, kickoff="2099-09-01T18:00:00+00:00", home_id=1, away_id=2, home_win=1),
        _game(
            2,
            week=2,
            kickoff="2099-09-08T18:00:00+00:00",
            home_id=1,
            away_id=3,
            home_win=0,
        ),
    ]
    attach_matrix_history(rows)
    early = copy.deepcopy(rows[0])
    rows[1]["home_win"] = 1
    attach_matrix_history(rows)
    assert rows[0]["home_entering_wins"] == early["home_entering_wins"]
    assert rows[0]["home_days_rest"] == early["home_days_rest"]
    assert rows[0]["home_sos"] == early["home_sos"]


def test_regular_feeds_postseason_but_not_reverse() -> None:
    rows = [
        _game(
            1,
            week=15,
            kickoff="2099-12-01T18:00:00+00:00",
            home_id=1,
            away_id=2,
            home_win=1,
            season_type="regular",
        ),
        _game(
            2,
            week=1,
            kickoff="2099-12-20T18:00:00+00:00",
            home_id=1,
            away_id=3,
            home_win=1,
            season_type="postseason",
        ),
    ]
    attach_matrix_history(rows)
    assert rows[1]["home_entering_wins"] == 1
    assert rows[1]["home_days_rest"] == 19
    # Mutate postseason outcome cannot change regular row after recompute
    before = copy.deepcopy(rows[0])
    rows[1]["home_win"] = 0
    attach_matrix_history(rows)
    assert rows[0]["home_entering_wins"] == before["home_entering_wins"]
