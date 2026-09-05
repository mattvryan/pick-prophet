"""Historical head-coach continuity capture and season-level features."""

from __future__ import annotations

import csv
import hashlib
import json
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pick_prophet.ingest.cfbd import BASE_URL, CFBDClient

FEATURE_COLUMNS = (
    "opening_coach_tenure_seasons_diff",
    "opening_first_year_coach_diff",
)


@dataclass(frozen=True)
class GameIdentity:
    game_id: int
    season: int
    kickoff_utc: str
    home_team_id: int
    away_team_id: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_coaches(rows: Any) -> None:
    if not isinstance(rows, list):
        raise TypeError("coaches response must be a list")
    coach_ids: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("coach rows must be objects")
        if row.get("id") is None or not isinstance(row.get("seasons"), list):
            raise ValueError("coach row requires id and seasons")
        coach_id = int(row["id"])
        if coach_id in coach_ids:
            raise ValueError(f"duplicate coach id: {coach_id}")
        coach_ids.add(coach_id)
        seen: set[tuple[int, int]] = set()
        for season in row["seasons"]:
            if season.get("teamId") is None or season.get("year") is None:
                raise ValueError("coach season requires teamId and year")
            key = (int(season["teamId"]), int(season["year"]))
            if key in seen:
                raise ValueError(f"duplicate coach team-season: {coach_id} {key}")
            seen.add(key)


def capture_coaches(
    target: Path,
    *,
    client: CFBDClient | None = None,
    retrieved_at: datetime | None = None,
) -> Path:
    """Capture the full coach history needed to determine school tenure."""

    if target.exists():
        raise FileExistsError(f"immutable M19 snapshot exists: {target}")
    target.mkdir(parents=True)
    rows = (client or CFBDClient()).get("/coaches", {})
    validate_coaches(rows)
    encoded = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    (target / "coaches.json").write_bytes(encoded)
    manifest = {
        "adapter_version": "m19-coaching-1.0.0",
        "endpoint": "/coaches",
        "params": {},
        "retrieved_at_utc": (retrieved_at or datetime.now(UTC))
        .astimezone(UTC)
        .isoformat(),
        "rows": len(rows),
        "season_rows": sum(len(row["seasons"]) for row in rows),
        "sha256": _sha256(encoded),
        "source": BASE_URL,
        "status": "complete",
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return target


def build_coaching_rows(
    games: list[GameIdentity], coaches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build season-opening tenure candidates without inferring change dates.

    When a team-season has multiple attributed coaches, a sole coach returning
    from the prior season is the season-opening coach. Other multi-coach cases
    remain unknown because the source does not expose team-specific start dates.
    """

    validate_coaches(coaches)
    assignments: dict[tuple[int, int], list[int]] = defaultdict(list)
    first_season: dict[tuple[int, int], int] = {}
    for coach in coaches:
        coach_id = int(coach["id"])
        for season in coach["seasons"]:
            team_id = int(season["teamId"])
            year = int(season["year"])
            assignments[(year, team_id)].append(coach_id)
            key = (coach_id, team_id)
            first_season[key] = min(year, first_season.get(key, year))

    output = []
    for game in games:
        values: dict[str, int | None] = {}
        for side, team_id in (
            ("home", game.home_team_id),
            ("away", game.away_team_id),
        ):
            candidates = assignments.get((game.season, team_id), [])
            continuing = [
                coach_id
                for coach_id in candidates
                if coach_id in assignments.get((game.season - 1, team_id), [])
            ]
            coach_id = candidates[0] if len(candidates) == 1 else None
            if coach_id is None and len(continuing) == 1:
                coach_id = continuing[0]
            tenure = (
                game.season - first_season[(coach_id, team_id)]
                if coach_id is not None
                else None
            )
            values[f"{side}_opening_coach_id"] = coach_id
            values[f"{side}_opening_coach_tenure_seasons"] = tenure
            values[f"{side}_opening_first_year_coach"] = (
                int(tenure == 0) if tenure is not None else None
            )
        home_tenure = values["home_opening_coach_tenure_seasons"]
        away_tenure = values["away_opening_coach_tenure_seasons"]
        home_first = values["home_opening_first_year_coach"]
        away_first = values["away_opening_first_year_coach"]
        output.append(
            {
                "game_id": game.game_id,
                "season": game.season,
                "kickoff_utc": game.kickoff_utc,
                **values,
                "opening_coach_tenure_seasons_diff": (
                    home_tenure - away_tenure
                    if home_tenure is not None and away_tenure is not None
                    else None
                ),
                "opening_first_year_coach_diff": (
                    home_first - away_first
                    if home_first is not None and away_first is not None
                    else None
                ),
            }
        )
    return output


def load_games(path: Path) -> list[GameIdentity]:
    with path.open(newline="") as handle:
        return [
            GameIdentity(
                game_id=int(row["game_id"]),
                season=int(row["season"]),
                kickoff_utc=row["kickoff_utc"],
                home_team_id=int(row["home_team_id"]),
                away_team_id=int(row["away_team_id"]),
            )
            for row in csv.DictReader(handle)
        ]


def write_feature_rows(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = ArgumentParser(description="Build M19 coaching-continuity features")
    parser.add_argument("--games", type=Path, required=True)
    parser.add_argument("--coaches", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    coaches = json.loads(args.coaches.read_text())
    write_feature_rows(build_coaching_rows(load_games(args.games), coaches), args.output)


if __name__ == "__main__":
    main()
