"""Point-in-time advanced-stat capture and chronological team-form features."""

from __future__ import annotations

import csv
import hashlib
import json
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from pick_prophet.ingest.cfbd import BASE_URL, CFBDClient

METRICS = ("ppa", "successRate", "explosiveness")
FEATURE_COLUMNS = tuple(
    f"form_{side}_{metric}_diff"
    for metric in METRICS
    for side in ("offense", "defense")
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture_advanced_season(
    season: int,
    target: Path,
    *,
    client: CFBDClient | None = None,
    retrieved_at: datetime | None = None,
) -> Path:
    """Capture one immutable season of completed-game advanced stats."""

    if target.exists():
        raise FileExistsError(f"immutable M18 snapshot exists: {target}")
    target.mkdir(parents=True)
    client = client or CFBDClient()
    rows = client.get("/stats/game/advanced", {"year": season})
    validate_advanced_rows(rows, expected_season=season)
    encoded = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    data_path = target / "advanced_game_stats.json"
    data_path.write_bytes(encoded)
    captured = (retrieved_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    manifest = {
        "adapter_version": "m18-1.0.0",
        "source": BASE_URL,
        "endpoint": "/stats/game/advanced",
        "params": {"year": season},
        "season": season,
        "retrieved_at_utc": captured,
        "rows": len(rows),
        "sha256": _sha256(encoded),
        "status": "complete",
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return target


def validate_advanced_rows(rows: Any, *, expected_season: int) -> None:
    if not isinstance(rows, list):
        raise TypeError("advanced stats response must be a list")
    seen: set[tuple[int, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("advanced stats rows must be objects")
        required = {"gameId", "season", "week", "team", "opponent", "offense", "defense"}
        missing = sorted(required - set(row))
        if missing:
            raise ValueError(f"advanced stats row missing fields: {missing}")
        if int(row["season"]) != expected_season:
            raise ValueError("advanced stats season mismatch")
        key = (int(row["gameId"]), str(row["team"]))
        if key in seen:
            raise ValueError(f"duplicate advanced team/game row: {key}")
        seen.add(key)
        for side in ("offense", "defense"):
            if not isinstance(row[side], dict):
                raise TypeError(f"{side} must be an object")
            for metric in METRICS:
                value = row[side].get(metric)
                if value is not None:
                    float(value)


@dataclass(frozen=True)
class GameIdentity:
    game_id: int
    season: int
    kickoff_utc: str
    home_team: str
    away_team: str


def _mean(history: dict[str, list[float]], team: str) -> float | None:
    values = history.get(team, [])
    return fmean(values) if values else None


def build_team_form_rows(
    games: list[GameIdentity], advanced_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build prior-only opponent-adjusted rolling differentials.

    Each observed team-game metric is centered on the opponent's prior rolling
    counterpart. The adjusted observation enters team history only after the
    pregame feature row for that game is emitted.
    """

    by_game: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in advanced_rows:
        by_game[int(row["gameId"])][str(row["team"])] = row

    histories: dict[tuple[int, str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    output: list[dict[str, Any]] = []
    for game in sorted(games, key=lambda item: (item.kickoff_utc, item.game_id)):
        rows = by_game.get(game.game_id, {})
        unknown = sorted(set(rows) - {game.home_team, game.away_team})
        if unknown:
            raise ValueError(f"advanced team identity mismatch game {game.game_id}: {unknown}")
        feature: dict[str, Any] = {
            "game_id": game.game_id,
            "season": game.season,
            "kickoff_utc": game.kickoff_utc,
            "prior_games_home": len(
                histories[(game.season, "offense", "ppa")].get(game.home_team, [])
            ),
            "prior_games_away": len(
                histories[(game.season, "offense", "ppa")].get(game.away_team, [])
            ),
        }
        for metric in METRICS:
            for side in ("offense", "defense"):
                history = histories[(game.season, side, metric)]
                home = _mean(history, game.home_team)
                away = _mean(history, game.away_team)
                feature[f"form_{side}_{metric}_diff"] = (
                    home - away if home is not None and away is not None else None
                )
        output.append(feature)

        if set(rows) != {game.home_team, game.away_team}:
            continue
        pending: list[tuple[tuple[int, str, str], str, float]] = []
        for team, opponent in (
            (game.home_team, game.away_team),
            (game.away_team, game.home_team),
        ):
            row = rows[team]
            for metric in METRICS:
                observed_offense = row["offense"].get(metric)
                opponent_defense = _mean(
                    histories[(game.season, "defense", metric)], opponent
                )
                if observed_offense is not None:
                    pending.append(
                        (
                            (game.season, "offense", metric),
                            team,
                            float(observed_offense) - (opponent_defense or 0.0),
                        )
                    )
                observed_defense = row["defense"].get(metric)
                opponent_offense = _mean(
                    histories[(game.season, "offense", metric)], opponent
                )
                if observed_defense is not None:
                    pending.append(
                        (
                            (game.season, "defense", metric),
                            team,
                            float(observed_defense) - (opponent_offense or 0.0),
                        )
                    )
        for history_key, team, value in pending:
            histories[history_key][team].append(value)
    return output


def load_games(path: Path) -> list[GameIdentity]:
    with path.open(newline="") as handle:
        return [
            GameIdentity(
                game_id=int(row["game_id"]),
                season=int(row["season"]),
                kickoff_utc=row["kickoff_utc"],
                home_team=row["home_team"],
                away_team=row["away_team"],
            )
            for row in csv.DictReader(handle)
        ]


def load_advanced_snapshots(root: Path) -> list[dict[str, Any]]:
    """Load captured observations, rejecting duplicate season captures."""

    paths = sorted(root.glob("*/*/advanced_game_stats.json"))
    seasons = [int(path.parents[1].name) for path in paths]
    duplicates = sorted(season for season in set(seasons) if seasons.count(season) > 1)
    if duplicates:
        raise ValueError(f"multiple M18 captures for seasons: {duplicates}")
    rows: list[dict[str, Any]] = []
    for path in paths:
        season = int(path.parents[1].name)
        captured = json.loads(path.read_text())
        validate_advanced_rows(captured, expected_season=season)
        rows.extend(captured)
    return rows


def write_feature_rows(rows: list[dict[str, Any]], path: Path) -> None:
    """Write the deterministic research feature frame consumed by M20."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "game_id",
        "season",
        "kickoff_utc",
        "prior_games_home",
        "prior_games_away",
        *FEATURE_COLUMNS,
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def coverage_by_season(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize candidate availability without inspecting game outcomes."""

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["season"])].append(row)
    output = []
    for season, season_rows in sorted(grouped.items()):
        complete = sum(
            all(row[column] is not None for column in FEATURE_COLUMNS)
            for row in season_rows
        )
        output.append(
            {
                "season": season,
                "games": len(season_rows),
                "games_with_complete_form": complete,
                "complete_form_rate": complete / len(season_rows),
                "games_with_both_teams_prior": sum(
                    int(row["prior_games_home"] > 0 and row["prior_games_away"] > 0)
                    for row in season_rows
                ),
            }
        )
    return output


def main() -> None:
    parser = ArgumentParser(description="Build chronological M18 team-form features")
    parser.add_argument("--games", type=Path, required=True)
    parser.add_argument("--snapshots", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    games = load_games(args.games)
    advanced = load_advanced_snapshots(args.snapshots)
    write_feature_rows(build_team_form_rows(games, advanced), args.output)


if __name__ == "__main__":
    main()
