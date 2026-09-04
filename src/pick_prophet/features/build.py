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


def _rating_index(
    rows: list[dict[str, Any]], value_key: str
) -> dict[tuple[int, str], float]:
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
    # Do not join season-level FPI/SP+ snapshots to historical games: a pull made
    # after the season contains future information. They remain raw-only until a
    # genuinely dated weekly archive is available.
    ratings = {"elo": _rating_index(load("elo"), "elo")}
    lines_by_id = {int(row["id"]): row.get("lines", []) for row in lines}
    output = []
    for game in games:
        # An FBS game includes at least one FBS program; this retains FBS-vs-FCS
        # games while excluding the thousands of lower-division-only matchups.
        home_classification = _get(game, "home_classification", "homeClassification")
        away_classification = _get(game, "away_classification", "awayClassification")
        if "fbs" not in {home_classification, away_classification}:
            continue
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
            "home_classification": home_classification,
            "away_classification": away_classification,
            "neutral_site": _get(game, "neutral_site", "neutralSite"),
            "home_points": hp,
            "away_points": ap,
            "home_win": None if hp is None or ap is None or hp == ap else int(hp > ap),
            **consensus_line(lines_by_id.get(game_id, [])),
            "is_pickem_game": None,
            "espn_home_pick_pct": None,
            "espn_expert_home_pct": None,
            "fpi_home": None,
            "fpi_away": None,
            "sp_home": None,
            "sp_away": None,
            "elo_home": _get(game, "home_pregame_elo", "homePregameElo"),
            "elo_away": _get(game, "away_pregame_elo", "awayPregameElo"),
            "source_snapshot": snapshot_dir.name,
        }
        # Use the preceding week. This conservative join avoids post-game values.
        feature_week = max(week - 1, 0)
        for poll in POLL_NAMES.values():
            row[f"{poll}_home_rank"] = ranks.get((feature_week, poll, home))
            row[f"{poll}_away_rank"] = ranks.get((feature_week, poll, away))
        for name, index in ratings.items():
            if row.get(f"{name}_home") is None:
                row[f"{name}_home"] = index.get((feature_week, home))
            if row.get(f"{name}_away") is None:
                row[f"{name}_away"] = index.get((feature_week, away))
        output.append(row)
    attach_history_features(output)
    return output


def _history_team_key(season: Any, team_id: Any, team_name: Any) -> tuple[Any, str, Any]:
    if team_id is not None and str(team_id).strip() != "":
        return (season, "id", int(team_id))
    return (season, "name", team_name)


def _win_pct(wins: int, losses: int) -> float | None:
    total = wins + losses
    if total <= 0:
        return None
    return wins / total


def attach_history_features(rows: list[dict[str, Any]]) -> None:
    """Add entering W-L, previous result, and SOS using only prior completed games.

    Mutates rows in place. Games are ordered by kickoff then game_id so a later
    result cannot change an earlier row. Incomplete games and ties do not update
    team records.
    """

    ordered = sorted(
        rows,
        key=lambda r: (
            str(r.get("kickoff_utc") or ""),
            int(r["game_id"]),
        ),
    )
    record: dict[tuple[Any, str, Any], tuple[int, int]] = {}
    previous: dict[tuple[Any, str, Any], int | None] = {}
    opponents_faced: dict[tuple[Any, str, Any], list[tuple[Any, str, Any]]] = {}

    for row in ordered:
        season = row.get("season")
        home_key = _history_team_key(season, row.get("home_team_id"), row.get("home_team"))
        away_key = _history_team_key(season, row.get("away_team_id"), row.get("away_team"))
        home_w, home_l = record.get(home_key, (0, 0))
        away_w, away_l = record.get(away_key, (0, 0))
        row["home_entering_wins"] = home_w
        row["home_entering_losses"] = home_l
        row["away_entering_wins"] = away_w
        row["away_entering_losses"] = away_l
        row["home_previous_result"] = previous.get(home_key)
        row["away_previous_result"] = previous.get(away_key)

        def sos_for(team_key: tuple[Any, str, Any]) -> float | None:
            faced = opponents_faced.get(team_key, [])
            values: list[float] = []
            for opp in faced:
                ow, ol = record.get(opp, (0, 0))
                pct = _win_pct(ow, ol)
                if pct is not None:
                    values.append(pct)
            if not values:
                return None
            return sum(values) / len(values)

        row["home_sos"] = sos_for(home_key)
        row["away_sos"] = sos_for(away_key)

        home_win = row.get("home_win")
        if home_win is None:
            continue
        # Update only after features are frozen for this kickoff.
        if int(home_win) == 1:
            record[home_key] = (home_w + 1, home_l)
            record[away_key] = (away_w, away_l + 1)
            previous[home_key] = 1
            previous[away_key] = 0
        else:
            record[home_key] = (home_w, home_l + 1)
            record[away_key] = (away_w + 1, away_l)
            previous[home_key] = 0
            previous[away_key] = 1
        opponents_faced.setdefault(home_key, []).append(away_key)
        opponents_faced.setdefault(away_key, []).append(home_key)


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
