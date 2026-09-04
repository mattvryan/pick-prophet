"""Leakage tests for point-in-time history features."""

from __future__ import annotations

import copy

from pick_prophet.features.build import attach_history_features


def _game(
    game_id: int,
    *,
    week: int,
    kickoff: str,
    home_id: int,
    away_id: int,
    home_points: int | None,
    away_points: int | None,
    season: int = 2024,
) -> dict:
    home_win = None
    if home_points is not None and away_points is not None and home_points != away_points:
        home_win = int(home_points > away_points)
    return {
        "game_id": game_id,
        "season": season,
        "week": week,
        "kickoff_utc": kickoff,
        "home_team": f"H{home_id}",
        "away_team": f"A{away_id}",
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_points": home_points,
        "away_points": away_points,
        "home_win": home_win,
    }


def test_entering_records_shift_within_season() -> None:
    rows = [
        _game(
            1,
            week=1,
            kickoff="2024-08-31T00:00:00Z",
            home_id=10,
            away_id=20,
            home_points=21,
            away_points=14,
        ),
        _game(
            2,
            week=2,
            kickoff="2024-09-07T00:00:00Z",
            home_id=10,
            away_id=30,
            home_points=10,
            away_points=17,
        ),
    ]
    attach_history_features(rows)
    assert rows[0]["home_entering_wins"] == 0
    assert rows[0]["home_entering_losses"] == 0
    assert rows[0]["home_previous_result"] is None
    assert rows[1]["home_entering_wins"] == 1
    assert rows[1]["home_entering_losses"] == 0
    assert rows[1]["home_previous_result"] == 1
    assert rows[1]["away_entering_wins"] == 0
    assert rows[1]["home_sos"] == 0.0  # week-1 opponent is 0-1 after week 1


def test_future_result_cannot_change_earlier_row() -> None:
    base = [
        _game(
            1,
            week=1,
            kickoff="2024-08-31T00:00:00Z",
            home_id=10,
            away_id=20,
            home_points=21,
            away_points=14,
        ),
        _game(
            2,
            week=2,
            kickoff="2024-09-07T00:00:00Z",
            home_id=10,
            away_id=30,
            home_points=7,
            away_points=3,
        ),
        _game(
            3,
            week=3,
            kickoff="2024-09-14T00:00:00Z",
            home_id=30,
            away_id=10,
            home_points=28,
            away_points=0,
        ),
    ]
    early = copy.deepcopy(base)
    attach_history_features(early)
    early_week1 = {
        k: early[0][k]
        for k in (
            "home_entering_wins",
            "home_entering_losses",
            "away_entering_wins",
            "away_entering_losses",
            "home_previous_result",
            "away_previous_result",
            "home_sos",
            "away_sos",
        )
    }
    early_week2 = {
        k: early[1][k]
        for k in (
            "home_entering_wins",
            "home_entering_losses",
            "home_previous_result",
            "home_sos",
        )
    }

    flipped = copy.deepcopy(base)
    # Flip the week-3 outcome: must not alter week-1 or week-2 features.
    flipped[2]["home_points"] = 0
    flipped[2]["away_points"] = 28
    flipped[2]["home_win"] = 0
    attach_history_features(flipped)
    flipped_week1 = {k: flipped[0][k] for k in early_week1}
    flipped_week2 = {k: flipped[1][k] for k in early_week2}
    assert flipped_week1 == early_week1
    assert flipped_week2 == early_week2


def test_incomplete_game_does_not_update_record() -> None:
    rows = [
        _game(
            1,
            week=1,
            kickoff="2024-08-31T00:00:00Z",
            home_id=10,
            away_id=20,
            home_points=None,
            away_points=None,
        ),
        _game(
            2,
            week=2,
            kickoff="2024-09-07T00:00:00Z",
            home_id=10,
            away_id=30,
            home_points=14,
            away_points=7,
        ),
    ]
    attach_history_features(rows)
    assert rows[1]["home_entering_wins"] == 0
    assert rows[1]["home_entering_losses"] == 0
    assert rows[1]["home_previous_result"] is None
    assert rows[1]["home_sos"] is None
