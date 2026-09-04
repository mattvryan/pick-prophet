"""Capture structured pre-game signals without producing recommendations."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pick_prophet.ingest.cfbd import CFBDClient
from pick_prophet.weekly.validate import validate_slate

SIGNALS_SCHEMA_VERSION = "weekly_signals.v1"
SIGNAL_FIELDS = [
    "display_order", "cfbd_game_id", "away_team", "home_team", "kickoff_utc",
    "neutral_site", "venue", "venue_id", "away_conference", "home_conference",
    "away_pregame_elo", "home_pregame_elo", "away_fpi", "home_fpi",
    "away_sp", "home_sp", "away_sp_rank", "home_sp_rank", "away_ap_rank",
    "home_ap_rank", "snapshot_at_utc",
]


class SignalsClient(Protocol):
    def get(self, path: str, params: dict[str, Any]) -> Any: ...


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stamp_now() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _iso(stamp: str) -> str:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(
        tzinfo=UTC
    ).isoformat().replace("+00:00", "Z")


def _ap_ranks(rankings: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for week in rankings:
        for poll in week.get("polls", []):
            if poll.get("poll") == "AP Top 25":
                result.update({row["school"]: int(row["rank"]) for row in poll["ranks"]})
    return result


def fetch_signals_snapshot(
    slate_path: Path | str,
    *,
    client: SignalsClient | None = None,
    snapshot: str | None = None,
) -> Path:
    slate_path = Path(slate_path)
    validation = validate_slate(slate_path)
    if not validation.ok:
        raise ValueError("slate validation failed:\n" + "\n".join(validation.errors))
    seasons = {int(row["season"]) for row in validation.rows}
    weeks = {int(row["contest_week"]) for row in validation.rows}
    if len(seasons) != 1 or len(weeks) != 1:
        raise ValueError("signals fetch requires exactly one season and contest week")
    season, week = seasons.pop(), weeks.pop()
    client = client or CFBDClient()
    requests = {
        "games": ("/games", {"year": season, "week": week, "seasonType": "regular"}),
        "rankings": ("/rankings", {"year": season, "week": week, "seasonType": "regular"}),
        "fpi": ("/ratings/fpi", {"year": season}),
        "sp": ("/ratings/sp", {"year": season}),
    }
    payloads = {name: client.get(path, params) for name, (path, params) in requests.items()}

    wanted_ids = {int(row["cfbd_game_id"]) for row in validation.rows}
    wanted_teams = {
        team for row in validation.rows for team in (row["away_team"], row["home_team"])
    }
    games = {int(row["id"]): row for row in payloads["games"] if int(row["id"]) in wanted_ids}
    fpi = {row["team"]: row for row in payloads["fpi"] if row["team"] in wanted_teams}
    sp = {row["team"]: row for row in payloads["sp"] if row["team"] in wanted_teams}
    ap = _ap_ranks(payloads["rankings"])
    snapshot = snapshot or _stamp_now()
    snapshot_at = _iso(snapshot)
    target = slate_path.parent / "signals" / snapshot
    if target.exists():
        raise FileExistsError(f"signals snapshot already exists: {target}")
    target.mkdir(parents=True)

    raw_dir = target / "raw"
    raw_dir.mkdir()
    for name, payload in payloads.items():
        (raw_dir / f"{name}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n"
        )

    rows = []
    for slate in validation.rows:
        game = games.get(int(slate["cfbd_game_id"]), {})
        away, home = slate["away_team"], slate["home_team"]
        rows.append({
            "display_order": slate["display_order"],
            "cfbd_game_id": slate["cfbd_game_id"],
            "away_team": away,
            "home_team": home,
            "kickoff_utc": game.get("startDate"),
            "neutral_site": game.get("neutralSite"),
            "venue": game.get("venue"),
            "venue_id": game.get("venueId"),
            "away_conference": game.get("awayConference"),
            "home_conference": game.get("homeConference"),
            "away_pregame_elo": game.get("awayPregameElo"),
            "home_pregame_elo": game.get("homePregameElo"),
            "away_fpi": fpi.get(away, {}).get("fpi"),
            "home_fpi": fpi.get(home, {}).get("fpi"),
            "away_sp": sp.get(away, {}).get("rating"),
            "home_sp": sp.get(home, {}).get("rating"),
            "away_sp_rank": sp.get(away, {}).get("ranking"),
            "home_sp_rank": sp.get(home, {}).get("ranking"),
            "away_ap_rank": ap.get(away),
            "home_ap_rank": ap.get(home),
            "snapshot_at_utc": snapshot_at,
        })
    signals_path = target / "signals.csv"
    with signals_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SIGNAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    coverage_fields = [
        "venue", "away_pregame_elo", "home_pregame_elo", "away_fpi", "home_fpi",
        "away_sp", "home_sp",
    ]
    manifest = {
        "schema_version": SIGNALS_SCHEMA_VERSION,
        "snapshot_at_utc": snapshot_at,
        "slate_path": str(slate_path),
        "slate_sha256": _sha256(slate_path),
        "requests": {name: params for name, (_, params) in requests.items()},
        "row_count": len(rows),
        "matched_games": len(games),
        "coverage": {
            field: sum(row[field] is not None for row in rows) / len(rows)
            for field in coverage_fields
        },
        "timing_note": (
            "FPI and SP+ are current season-level values captured before slate locks; "
            "game pregame Elo is used instead of the sparse week endpoint."
        ),
        "files": {
            "signals.csv": _sha256(signals_path),
            **{f"raw/{name}.json": _sha256(raw_dir / f"{name}.json") for name in payloads},
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return target
