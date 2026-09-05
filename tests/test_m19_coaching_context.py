from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pick_prophet.research.m19_coaching_context import (
    GameIdentity,
    build_coaching_rows,
    capture_coaches,
    validate_coaches,
)


def _coach(coach_id: int, assignments: list[tuple[int, int]]) -> dict:
    return {
        "id": coach_id,
        "firstName": "Coach",
        "lastName": str(coach_id),
        "seasons": [
            {"teamId": team_id, "year": year} for team_id, year in assignments
        ],
    }


def test_tenure_is_derived_from_first_school_season() -> None:
    coaches = [
        _coach(1, [(10, 2022), (10, 2023), (10, 2024)]),
        _coach(2, [(20, 2024)]),
    ]
    games = [GameIdentity(1, 2024, "2024-09-01T00:00:00Z", 10, 20)]
    row = build_coaching_rows(games, coaches)[0]
    assert row["home_opening_coach_tenure_seasons"] == 2
    assert row["away_opening_first_year_coach"] == 1
    assert row["opening_coach_tenure_seasons_diff"] == 2
    assert row["opening_first_year_coach_diff"] == -1


def test_returning_coach_resolves_season_opener_before_later_change() -> None:
    coaches = [
        _coach(1, [(10, 2023), (10, 2024)]),
        _coach(2, [(10, 2024)]),
        _coach(3, [(20, 2024)]),
    ]
    row = build_coaching_rows(
        [GameIdentity(1, 2024, "2024-09-01T00:00:00Z", 10, 20)], coaches
    )[0]
    assert row["home_opening_coach_id"] == 1
    assert row["home_opening_coach_tenure_seasons"] == 1


def test_ambiguous_multi_coach_team_season_is_unknown() -> None:
    coaches = [
        _coach(1, [(10, 2024)]),
        _coach(2, [(10, 2024)]),
        _coach(3, [(20, 2024)]),
    ]
    row = build_coaching_rows(
        [GameIdentity(1, 2024, "2024-09-01T00:00:00Z", 10, 20)], coaches
    )[0]
    assert row["home_opening_coach_id"] is None
    assert row["home_opening_first_year_coach"] is None
    assert row["opening_first_year_coach_diff"] is None


def test_missing_assignment_remains_unknown() -> None:
    row = build_coaching_rows(
        [GameIdentity(1, 2024, "2024-09-01T00:00:00Z", 10, 20)],
        [_coach(1, [(10, 2024)])],
    )[0]
    assert row["away_opening_coach_id"] is None
    assert row["opening_coach_tenure_seasons_diff"] is None


def test_future_assignment_cannot_change_earlier_context() -> None:
    games = [GameIdentity(1, 2024, "2024-09-01T00:00:00Z", 10, 20)]
    base = [_coach(1, [(10, 2023), (10, 2024)]), _coach(2, [(20, 2024)])]
    future = [*base, _coach(3, [(10, 2025)])]
    assert build_coaching_rows(games, base) == build_coaching_rows(games, future)


class _Client:
    def get(self, path: str, params: dict) -> list[dict]:
        assert (path, params) == ("/coaches", {})
        return [_coach(1, [(10, 2024)])]


def test_capture_is_immutable_and_manifested(tmp_path: Path) -> None:
    target = tmp_path / "snapshot"
    capture_coaches(
        target,
        client=_Client(),  # type: ignore[arg-type]
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["season_rows"] == 1
    with pytest.raises(FileExistsError):
        capture_coaches(target, client=_Client())  # type: ignore[arg-type]


def test_duplicate_coach_id_fails() -> None:
    coach = _coach(1, [(10, 2024)])
    with pytest.raises(ValueError, match="duplicate coach id"):
        validate_coaches([coach, coach])
