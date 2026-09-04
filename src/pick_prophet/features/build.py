"""Build a canonical, point-in-time game table from raw snapshots."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .market import consensus_line

POLL_NAMES = {
    "AP Top 25": "ap",
    "Coaches Poll": "coaches",
    "Playoff Committee Rankings": "cfp",
}


def _get(row: dict[str, Any], snake: str, camel: str | None = None) -> Any:
    return row.get(snake, row.get(camel or snake))


def _rank_index(rows: list[dict[str, Any]]) -> dict[tuple[int, str, str], int]:
    result: dict[tuple[int, str, str], int] = {}
    for weekly in rows:
        week = int(weekly["week"])
        for poll in weekly.get("polls", []):
            prefix = POLL_NAMES.get(poll.get("poll"))
            if not prefix:
                continue
            for rank in poll.get("ranks", []):
                result[(week, prefix, rank["school"])] = int(rank["rank"])
    return result


def _rating_index(rows: list[dict[str, Any]], value_key: str) -> dict[tuple[int, str], float]:
    result = {}
    for row in rows:
        value = row.get(value_key, row.get("rating"))
        if value is not None and row.get("week") is not None:
            result[(int(row["week"]), row["team"])] = float(value)
    return result


def build_rows(snapshot_dir: Path) -> list[dict[str, Any]]:
    def load(name: str) -> Any:
        return json.loads((snapshot_dir / f"{name}.json").read_text())

    games, lines = load("games"), load("lines")
    ranks = _rank_index(load("rankings"))
    ratings = {
        "fpi": _rating_index(load("fpi"), "fpi"),
        "sp": _rating_index(load("sp"), "rating"),
        "elo": _rating_index(load("elo"), "elo"),
    }
    lines_by_id = {int(row["id"]): row.get("lines", []) for row in lines}
    output = []
    for game in games:
        game_id = int(game["id"])
        week = int(game["week"])
        home = _get(game, "home_team", "homeTeam")
        away = _get(game, "away_team", "awayTeam")
        hp = _get(game, "home_points", "homePoints")
        ap = _get(game, "away_points", "awayPoints")
        row = {
            "game_id": game_id,
            "season": _get(game, "season"),
            "week": week,
            "season_type": _get(game, "season_type", "seasonType"),
            "kickoff_utc": _get(game, "start_date", "startDate"),
            "home_team": home,
            "away_team": away,
            "home_team_id": _get(game, "home_id", "homeId"),
            "away_team_id": _get(game, "away_id", "awayId"),
            "home_conference": _get(game, "home_conference", "homeConference"),
            "away_conference": _get(game, "away_conference", "awayConference"),
            "neutral_site": _get(game, "neutral_site", "neutralSite"),
            "home_points": hp,
            "away_points": ap,
            "home_win": None if hp is None or ap is None or hp == ap else int(hp > ap),
            **consensus_line(lines_by_id.get(game_id, [])),
            "is_pickem_game": None,
            "espn_home_pick_pct": None,
            "espn_expert_home_pct": None,
            "source_snapshot": snapshot_dir.name,
        }
        # Use the preceding week. This conservative join avoids post-game values.
        feature_week = max(week - 1, 0)
        for poll in POLL_NAMES.values():
            row[f"{poll}_home_rank"] = ranks.get((feature_week, poll, home))
            row[f"{poll}_away_rank"] = ranks.get((feature_week, poll, away))
        for name, index in ratings.items():
            row[f"{name}_home"] = index.get((feature_week, home))
            row[f"{name}_away"] = index.get((feature_week, away))
        output.append(row)
    return output


def merge_pickem(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open(newline="") as handle:
        external = {int(r["game_id"]): r for r in csv.DictReader(handle)}
    for row in rows:
        if match := external.get(row["game_id"]):
            row["is_pickem_game"] = match["is_pickem_game"].lower() == "true"
            for field in ("espn_home_pick_pct", "espn_expert_home_pct"):
                row[field] = float(match[field]) if match.get(field) else None


def write_dataset(rows: list[dict[str, Any]], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("cannot write an empty dataset")
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    quality = {
        "rows": len(rows),
        "completed_games": sum(r["home_win"] is not None for r in rows),
        "known_pickem_games": sum(r["is_pickem_game"] is True for r in rows),
        "missing_fraction": {
            key: sum(r[key] is None for r in rows) / len(rows) for key in rows[0]
        },
    }
    report = output.with_suffix(".quality.json")
    report.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n")
    return report
