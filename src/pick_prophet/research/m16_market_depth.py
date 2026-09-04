"""M16 historical market-depth audit and provider-neutral contract."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

REQUIRED_QUOTE_FIELDS = {
    "game_id",
    "provider",
    "observed_at_utc",
    "home_moneyline",
    "away_moneyline",
}


def validate_quote(row: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_QUOTE_FIELDS - set(row))
    if missing:
        raise ValueError(f"market quote missing fields: {missing}")
    if not str(row["observed_at_utc"]).endswith("Z"):
        raise ValueError("observed_at_utc must be explicit UTC")
    if row["home_moneyline"] in {None, ""} or row["away_moneyline"] in {None, ""}:
        raise ValueError("both moneyline sides are required")


def audit_matrix(matrix_path: Path, output_path: Path) -> dict[str, Any]:
    with matrix_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("matrix is empty")
    seasons = Counter(str(int(row["season"])) for row in rows)
    timing = Counter(row.get("market_timing", "") for row in rows)
    open_complete = sum(
        bool(row.get("spread_home_open")) and bool(row.get("total_open"))
        for row in rows
    )
    movement_complete = sum(
        bool(row.get("spread_move_home")) and bool(row.get("total_move"))
        for row in rows
    )
    payload = {
        "artifact_version": "1.0.0",
        "protocol_version": "2.0.0",
        "rows": len(rows),
        "rows_by_season": dict(sorted(seasons.items())),
        "market_timing_counts": dict(sorted(timing.items())),
        "complete_open_spread_and_total_rows": open_complete,
        "complete_movement_rows": movement_complete,
        "timestamped_historical_quote_rows": 0,
        "status": "blocked_paid_timestamped_archive_required",
        "contains_2026_outcomes": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload
