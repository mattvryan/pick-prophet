"""Fetch completed slate results from CFBD into an immutable weekly CSV."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pick_prophet.ingest.cfbd import CFBDClient
from pick_prophet.weekly.validate import validate_slate

RESULTS_SCHEMA_VERSION = "weekly_results.v1"
RESULT_FIELDS = [
    "display_order",
    "cfbd_game_id",
    "away_team",
    "home_team",
    "away_points",
    "home_points",
    "winner",
    "total_points",
    "completed",
    "source",
    "captured_at_utc",
]


class ResultsClient(Protocol):
    def get(self, path: str, params: dict[str, Any]) -> Any: ...


def _stamp_now() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _iso(stamp: str) -> str:
    return (
        datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
        .replace(tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def fetch_results(
    *,
    week_dir: Path | str,
    slate_path: Path | str | None = None,
    client: ResultsClient | None = None,
    snapshot: str | None = None,
    allow_incomplete: bool = False,
) -> Path:
    """Write completed scores for every slate game under results/<stamp>/."""

    week_dir = Path(week_dir)
    slate_path = Path(slate_path) if slate_path else week_dir / "slate.csv"
    validation = validate_slate(slate_path)
    if not validation.ok:
        raise ValueError("slate validation failed:\n" + "\n".join(validation.errors))

    seasons = {int(row["season"]) for row in validation.rows}
    weeks = {int(row["contest_week"]) for row in validation.rows}
    if len(seasons) != 1 or len(weeks) != 1:
        raise ValueError("results fetch requires exactly one season and contest week")
    season, week = seasons.pop(), weeks.pop()

    client = client or CFBDClient()
    payload = client.get(
        "/games", {"year": season, "week": week, "seasonType": "regular"}
    )
    by_id = {int(row["id"]): row for row in payload}

    stamp = snapshot or _stamp_now()
    captured_at = _iso(stamp)
    target_dir = week_dir / "results" / stamp
    if target_dir.exists():
        raise FileExistsError(f"results snapshot already exists: {target_dir}")

    rows: list[dict[str, Any]] = []
    incomplete: list[str] = []
    for slate in validation.rows:
        game_id = int(slate["cfbd_game_id"])
        game = by_id.get(game_id)
        if game is None:
            incomplete.append(f"{game_id}: missing from CFBD /games")
            continue
        away_points = game.get("awayPoints")
        home_points = game.get("homePoints")
        completed = bool(game.get("completed")) and away_points is not None and home_points is not None
        if not completed:
            incomplete.append(
                f"{game_id}: {slate['away_team']} at {slate['home_team']} incomplete"
            )
            winner = None
            total = None
        elif int(home_points) > int(away_points):
            winner = slate["home_team"]
            total = int(home_points) + int(away_points)
        elif int(away_points) > int(home_points):
            winner = slate["away_team"]
            total = int(home_points) + int(away_points)
        else:
            winner = None
            total = int(home_points) + int(away_points)
            incomplete.append(f"{game_id}: tie score not supported for Pick'em grading")

        rows.append(
            {
                "display_order": slate["display_order"],
                "cfbd_game_id": slate["cfbd_game_id"],
                "away_team": slate["away_team"],
                "home_team": slate["home_team"],
                "away_points": away_points,
                "home_points": home_points,
                "winner": winner,
                "total_points": total,
                "completed": completed and winner is not None,
                "source": "cfbd:/games",
                "captured_at_utc": captured_at,
            }
        )

    if incomplete and not allow_incomplete:
        raise ValueError(
            "cannot fetch complete results yet:\n" + "\n".join(incomplete)
        )

    target_dir.mkdir(parents=True)
    output = target_dir / "results.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (target_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": RESULTS_SCHEMA_VERSION,
                "captured_at_utc": captured_at,
                "slate_path": str(slate_path),
                "row_count": len(rows),
                "complete_count": sum(1 for row in rows if row["completed"]),
                "incomplete": incomplete,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output
