"""Market-total baseline for ESPN Pick'em tiebreakers."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from pick_prophet.weekly.validate import parse_timestamp, validate_slate

SCHEMA_VERSION = "weekly_tiebreaker.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recommend_tiebreaker(
    slate_path: Path | str,
    market_path: Path | str,
    *,
    game_id: str,
    as_of: str,
    output_dir: Path | str,
    generated_at: str | None = None,
) -> dict[str, Path]:
    """Recommend a whole-number total from a consensus market total."""

    slate_path = Path(slate_path)
    market_path = Path(market_path)
    output_dir = Path(output_dir)
    validation = validate_slate(slate_path, as_of=as_of)
    if not validation.ok:
        raise ValueError("slate validation failed:\n" + "\n".join(validation.errors))

    slate_matches = [
        row for row in validation.rows if str(row["cfbd_game_id"]) == str(game_id)
    ]
    if len(slate_matches) != 1:
        raise ValueError(
            f"tiebreaker game_id={game_id} not found exactly once in slate"
        )
    slate_row = slate_matches[0]

    with market_path.open(newline="", encoding="utf-8") as handle:
        market_matches = [
            row
            for row in csv.DictReader(handle)
            if str(row.get("cfbd_game_id", "")) == str(game_id)
        ]
    if len(market_matches) != 1:
        raise ValueError(
            f"tiebreaker game_id={game_id} not found exactly once in market snapshot"
        )
    market_row = market_matches[0]
    if (
        market_row.get("away_team") != slate_row["away_team"]
        or market_row.get("home_team") != slate_row["home_team"]
    ):
        raise ValueError(f"market/slate team mismatch for game_id={game_id}")
    if market_row.get("status") != "ok":
        raise ValueError(f"market status is not ok for game_id={game_id}")

    try:
        consensus_total = Decimal(market_row["total"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"missing or invalid market total for game_id={game_id}"
        ) from exc
    if consensus_total <= 0:
        raise ValueError(f"market total must be positive for game_id={game_id}")

    snapshot_at = market_row.get("snapshot_at_utc", "")
    if snapshot_at:
        snapshot_dt = parse_timestamp(snapshot_at, "snapshot_at_utc", "market")
        as_of_dt = parse_timestamp(as_of, "as_of", "command")
        if snapshot_dt is not None and as_of_dt is not None and snapshot_dt > as_of_dt:
            raise ValueError("market snapshot was captured after --as-of")

    recommended_total = int(consensus_total.quantize(Decimal(1), ROUND_HALF_UP))
    generated = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "generated_at": generated,
        "cfbd_game_id": str(game_id),
        "away_team": slate_row["away_team"],
        "home_team": slate_row["home_team"],
        "neutral_site": slate_row["neutral_site"],
        "lock_at_utc": slate_row["lock_at_utc"],
        "market_snapshot_at_utc": snapshot_at or None,
        "consensus_market_total": float(consensus_total),
        "recommended_integer_total": recommended_total,
        "rounding_rule": "nearest integer; .5 rounds up",
        "method": "consensus market over/under baseline",
        "slate_sha256": _sha256(slate_path),
        "market_sha256": _sha256(market_path),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "tiebreaker.json"
    card_path = output_dir / "tiebreaker.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    card_path.write_text(
        "\n".join(
            [
                "# Pick'em tiebreaker",
                "",
                f"- Matchup: **{slate_row['away_team']} at {slate_row['home_team']}**",
                f"- Consensus market total: **{consensus_total}**",
                f"- Recommended ESPN entry: **{recommended_total} points**",
                "- Method: consensus market total, rounded to the nearest integer; .5 up",
                f"- As of: `{as_of}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json": json_path, "card": card_path}
