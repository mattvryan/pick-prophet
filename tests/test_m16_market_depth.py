from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pick_prophet.research.m16_market_depth import audit_matrix, validate_quote


def test_quote_requires_timestamp_and_both_sides() -> None:
    row = {
        "game_id": 1,
        "provider": "book",
        "observed_at_utc": "2024-09-01T12:00:00Z",
        "home_moneyline": -120,
        "away_moneyline": 110,
    }
    validate_quote(row)
    row["away_moneyline"] = None
    with pytest.raises(ValueError, match="both moneyline sides"):
        validate_quote(row)
    row["away_moneyline"] = 110
    row["observed_at_utc"] = "2024-09-01 12:00"
    with pytest.raises(ValueError, match="explicit UTC"):
        validate_quote(row)


def test_audit_never_invents_market_depth(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.csv"
    with matrix.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "season",
                "market_timing",
                "spread_home_open",
                "total_open",
                "spread_move_home",
                "total_move",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "season": 2025,
                "market_timing": "closing_like",
                "spread_home_open": "",
                "total_open": "",
                "spread_move_home": "",
                "total_move": "",
            }
        )
    out = tmp_path / "audit.json"
    result = audit_matrix(matrix, out)
    assert result["timestamped_historical_quote_rows"] == 0
    assert result["complete_movement_rows"] == 0
    assert result["contains_2026_outcomes"] is False
    assert json.loads(out.read_text()) == result
