from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pick_prophet.research.m18_team_form import (
    GameIdentity,
    build_team_form_rows,
    capture_advanced_season,
    coverage_by_season,
    load_advanced_snapshots,
    validate_advanced_rows,
)


def _stat(value: float) -> dict[str, float]:
    return {"ppa": value, "successRate": value, "explosiveness": value}


def _row(game: int, week: int, team: str, opponent: str, value: float) -> dict:
    return {
        "gameId": game,
        "season": 2024,
        "week": week,
        "team": team,
        "opponent": opponent,
        "offense": _stat(value),
        "defense": _stat(-value),
    }


def test_future_game_mutation_cannot_change_earlier_features() -> None:
    games = [
        GameIdentity(1, 2024, "2024-09-01T00:00:00Z", "A", "B"),
        GameIdentity(2, 2024, "2024-09-08T00:00:00Z", "A", "B"),
        GameIdentity(3, 2024, "2024-09-15T00:00:00Z", "A", "B"),
    ]
    rows = [
        _row(1, 1, "A", "B", 1.0),
        _row(1, 1, "B", "A", -1.0),
        _row(2, 2, "A", "B", 2.0),
        _row(2, 2, "B", "A", -2.0),
        _row(3, 3, "A", "B", 3.0),
        _row(3, 3, "B", "A", -3.0),
    ]
    base = build_team_form_rows(games, rows)
    rows[-1]["offense"]["ppa"] = 999.0
    mutated = build_team_form_rows(games, rows)
    assert base == mutated


def test_current_game_does_not_enter_its_pregame_row() -> None:
    games = [GameIdentity(1, 2024, "2024-09-01T00:00:00Z", "A", "B")]
    features = build_team_form_rows(
        games, [_row(1, 1, "A", "B", 1.0), _row(1, 1, "B", "A", -1.0)]
    )
    assert features[0]["prior_games_home"] == 0
    assert features[0]["form_offense_ppa_diff"] is None


def test_identity_mismatch_fails() -> None:
    games = [GameIdentity(1, 2024, "2024-09-01T00:00:00Z", "A", "B")]
    with pytest.raises(ValueError, match="identity mismatch"):
        build_team_form_rows(games, [_row(1, 1, "Wrong", "B", 1.0)])


class _Client:
    def get(self, path: str, params: dict) -> list[dict]:
        assert path == "/stats/game/advanced"
        assert params == {"year": 2024}
        return [_row(1, 1, "A", "B", 1.0)]


def test_capture_is_immutable_and_manifested(tmp_path: Path) -> None:
    target = tmp_path / "snapshot"
    capture_advanced_season(
        2024,
        target,
        client=_Client(),  # type: ignore[arg-type]
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert (target / "manifest.json").is_file()
    with pytest.raises(FileExistsError):
        capture_advanced_season(2024, target, client=_Client())  # type: ignore[arg-type]


def test_schema_and_duplicates_fail() -> None:
    row = _row(1, 1, "A", "B", 1.0)
    with pytest.raises(ValueError, match="duplicate"):
        validate_advanced_rows([row, row], expected_season=2024)


def test_snapshot_loader_rejects_multiple_captures(tmp_path: Path) -> None:
    for stamp in ("first", "second"):
        target = tmp_path / "2024" / stamp
        capture_advanced_season(2024, target, client=_Client())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="multiple M18 captures"):
        load_advanced_snapshots(tmp_path)


def test_coverage_does_not_require_targets() -> None:
    rows = build_team_form_rows(
        [
            GameIdentity(1, 2024, "2024-09-01T00:00:00Z", "A", "B"),
            GameIdentity(2, 2024, "2024-09-08T00:00:00Z", "A", "B"),
        ],
        [
            _row(1, 1, "A", "B", 1.0),
            _row(1, 1, "B", "A", -1.0),
            _row(2, 2, "A", "B", 2.0),
            _row(2, 2, "B", "A", -2.0),
        ],
    )
    assert coverage_by_season(rows) == [
        {
            "season": 2024,
            "games": 2,
            "games_with_complete_form": 1,
            "complete_form_rate": 0.5,
            "games_with_both_teams_prior": 1,
        }
    ]
