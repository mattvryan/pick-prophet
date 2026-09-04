"""Compare game-level pregame Elo values with prior-week Elo snapshots."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, median
from typing import Any, Literal

DEFAULT_TOLERANCE = 1.0
DEFAULT_SEASON_TYPE = "regular"
PERCENTILE_METHOD = "sorted_index"

AGGREGATE_COLUMNS = (
    "season",
    "season_type",
    "week",
    "n_sides",
    "n_both_present",
    "n_exact_match",
    "exact_match_rate",
    "n_within_tolerance",
    "within_tolerance_rate",
    "mean_abs_delta",
    "median_abs_delta",
    "p90_abs_delta",
    "p95_abs_delta",
    "max_abs_delta",
    "n_pregame_null",
    "pregame_null_rate",
    "n_weekly_null",
    "weekly_null_rate",
    "n_pregame_only",
    "n_weekly_only",
    "n_name_fallback_joins",
)


class ConflictError(Exception):
    """Raised when one weekly Elo key has multiple rating values."""


@dataclass(frozen=True)
class EloKey:
    season: int
    season_type: str
    week: int
    team_key_type: Literal["id", "name"]
    team_key: str | int


class WeeklyEloIndex(Mapping[EloKey, float]):
    """Weekly Elo lookup with duplicate and key-type audit counters."""

    def __init__(
        self,
        values: dict[EloKey, float],
        *,
        source_row_count: int,
        identical_duplicate_count: int,
    ) -> None:
        self._values = values
        self.source_row_count = source_row_count
        self.identical_duplicate_count = identical_duplicate_count
        self.indexed_key_count = len(values)
        self.id_key_count = sum(key.team_key_type == "id" for key in values)
        self.name_key_count = sum(key.team_key_type == "name" for key in values)

    def __getitem__(self, key: EloKey) -> float:
        return self._values[key]

    def __iter__(self) -> Iterator[EloKey]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


@dataclass(frozen=True)
class SideCompare:
    game_id: int
    side: Literal["home", "away"]
    season: int
    season_type: str
    week: int
    feature_week: int
    team_id: int | None
    team_name: str
    pregame_elo: float | None
    weekly_elo: float | None
    join_key_type: Literal["id", "name"] | None
    abs_delta: float | None
    exact_match: bool | None
    within_tolerance: bool | None


def _get(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _read_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list) or not all(
        isinstance(row, dict) for row in payload
    ):
        raise ValueError(f"{path} must contain a JSON list of objects")
    return payload


def _season_type(value: Any) -> str:
    if value is None:
        return DEFAULT_SEASON_TYPE
    return str(value).strip().lower()


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def load_games(path: Path) -> list[dict]:
    """Load and normalize CFBD games, retaining games involving an FBS team."""

    games: list[dict[str, Any]] = []
    for row in _read_json_rows(path):
        home_classification = (
            str(_get(row, "home_classification", "homeClassification") or "")
            .strip()
            .lower()
        )
        away_classification = (
            str(_get(row, "away_classification", "awayClassification") or "")
            .strip()
            .lower()
        )
        if "fbs" not in {home_classification, away_classification}:
            continue

        games.append(
            {
                "game_id": int(_get(row, "game_id", "id")),
                "season": int(_get(row, "season")),
                "week": int(_get(row, "week")),
                "season_type": _season_type(_get(row, "season_type", "seasonType")),
                "start_date": _get(row, "start_date", "startDate"),
                "home_team_id": _optional_int(
                    _get(row, "home_team_id", "home_id", "homeId")
                ),
                "away_team_id": _optional_int(
                    _get(row, "away_team_id", "away_id", "awayId")
                ),
                "home_team": str(_get(row, "home_team", "homeTeam") or "").strip(),
                "away_team": str(_get(row, "away_team", "awayTeam") or "").strip(),
                "home_classification": home_classification,
                "away_classification": away_classification,
                "home_pregame_elo": _optional_float(
                    _get(row, "home_pregame_elo", "homePregameElo")
                ),
                "away_pregame_elo": _optional_float(
                    _get(row, "away_pregame_elo", "awayPregameElo")
                ),
            }
        )
    return games


def load_weekly_elo(path: Path) -> WeeklyEloIndex:
    """Load weekly Elo values and reject conflicting duplicate keys."""

    rows = _read_json_rows(path)
    values: dict[EloKey, float] = {}
    identical_duplicate_count = 0

    for row in rows:
        team_id = _optional_int(_get(row, "team_id", "teamId"))
        if team_id is not None:
            key_type: Literal["id", "name"] = "id"
            team_key: str | int = team_id
        else:
            key_type = "name"
            team_key = str(_get(row, "team", "team_name", "teamName") or "").strip()

        key = EloKey(
            season=int(_get(row, "season", "year")),
            season_type=_season_type(_get(row, "season_type", "seasonType")),
            week=int(_get(row, "week")),
            team_key_type=key_type,
            team_key=team_key,
        )
        rating = float(_get(row, "elo", "rating"))
        if key in values:
            if values[key] != rating:
                raise ConflictError(
                    f"Conflicting weekly Elo values for {key}: "
                    f"{values[key]} and {rating}"
                )
            identical_duplicate_count += 1
            continue
        values[key] = rating

    return WeeklyEloIndex(
        values,
        source_row_count=len(rows),
        identical_duplicate_count=identical_duplicate_count,
    )


def _weekly_lookup(
    weekly: Mapping[EloKey, float],
    *,
    season: int,
    season_type: str,
    feature_week: int,
    team_id: int | None,
    team_name: str,
) -> tuple[float | None, Literal["id", "name"] | None]:
    if team_id is not None:
        id_key = EloKey(season, season_type, feature_week, "id", team_id)
        if id_key in weekly:
            return weekly[id_key], "id"

    name_key = EloKey(season, season_type, feature_week, "name", team_name)
    if team_name and name_key in weekly:
        return weekly[name_key], "name"
    return None, None


def compare_snapshot(
    games: list[dict],
    weekly_index: WeeklyEloIndex,
    *,
    tolerance: float,
) -> list[SideCompare]:
    """Compare each retained game side against its prior-week Elo value."""

    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")

    comparisons: list[SideCompare] = []
    for game in games:
        feature_week = max(int(game["week"]) - 1, 0)
        for side in ("home", "away"):
            team_id = game[f"{side}_team_id"]
            team_name = game[f"{side}_team"]
            pregame_elo = game[f"{side}_pregame_elo"]
            weekly_elo, join_key_type = _weekly_lookup(
                weekly_index,
                season=game["season"],
                season_type=game["season_type"],
                feature_week=feature_week,
                team_id=team_id,
                team_name=team_name,
            )
            abs_delta = (
                abs(pregame_elo - weekly_elo)
                if pregame_elo is not None and weekly_elo is not None
                else None
            )
            comparisons.append(
                SideCompare(
                    game_id=game["game_id"],
                    side=side,
                    season=game["season"],
                    season_type=game["season_type"],
                    week=game["week"],
                    feature_week=feature_week,
                    team_id=team_id,
                    team_name=team_name,
                    pregame_elo=pregame_elo,
                    weekly_elo=weekly_elo,
                    join_key_type=join_key_type,
                    abs_delta=abs_delta,
                    exact_match=abs_delta == 0 if abs_delta is not None else None,
                    within_tolerance=(
                        abs_delta <= tolerance if abs_delta is not None else None
                    ),
                )
            )
    return comparisons


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _sorted_index_percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def aggregate_sides(sides: list[SideCompare]) -> list[dict]:
    """Aggregate side comparisons by game season, season type, and week."""

    grouped: dict[tuple[int, str, int], list[SideCompare]] = defaultdict(list)
    for side in sides:
        grouped[(side.season, side.season_type, side.week)].append(side)

    rows: list[dict[str, Any]] = []
    for (season, season_type, week), group in sorted(grouped.items()):
        n_sides = len(group)
        both = [
            side
            for side in group
            if side.pregame_elo is not None and side.weekly_elo is not None
        ]
        deltas = [side.abs_delta for side in both if side.abs_delta is not None]
        n_both = len(both)
        n_exact = sum(side.exact_match is True for side in both)
        n_within = sum(side.within_tolerance is True for side in both)
        n_pregame_null = sum(side.pregame_elo is None for side in group)
        n_weekly_null = sum(side.weekly_elo is None for side in group)
        rows.append(
            {
                "season": season,
                "season_type": season_type,
                "week": week,
                "n_sides": n_sides,
                "n_both_present": n_both,
                "n_exact_match": n_exact,
                "exact_match_rate": _rate(n_exact, n_both),
                "n_within_tolerance": n_within,
                "within_tolerance_rate": _rate(n_within, n_both),
                "mean_abs_delta": fmean(deltas) if deltas else None,
                "median_abs_delta": median(deltas) if deltas else None,
                "p90_abs_delta": _sorted_index_percentile(deltas, 0.90),
                "p95_abs_delta": _sorted_index_percentile(deltas, 0.95),
                "max_abs_delta": max(deltas) if deltas else None,
                "n_pregame_null": n_pregame_null,
                "pregame_null_rate": _rate(n_pregame_null, n_sides),
                "n_weekly_null": n_weekly_null,
                "weekly_null_rate": _rate(n_weekly_null, n_sides),
                "n_pregame_only": sum(
                    side.pregame_elo is not None and side.weekly_elo is None
                    for side in group
                ),
                "n_weekly_only": sum(
                    side.pregame_elo is None and side.weekly_elo is not None
                    for side in group
                ),
                "n_name_fallback_joins": sum(
                    side.join_key_type == "name" for side in group
                ),
            }
        )
    return rows


def write_aggregate_csv(rows: list[dict], path: Path) -> None:
    """Write aggregate rows with the stable research contract header."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AGGREGATE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
