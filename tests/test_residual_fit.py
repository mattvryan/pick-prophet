"""Integration tests for M08 residual walk-forward."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pick_prophet.models.fixed_offset_logit import sigmoid
from pick_prophet.models.residual_fit import (
    fit_residual_walkforward,
    validate_baseline_consistency,
)
from pick_prophet.models.residual_variants import VARIANTS


def _row(
    game_id: int,
    season: int,
    *,
    week: int = 2,
    logit: float = 0.0,
    y: int = 1,
    conference: str = "A",
    spread: float | None = -3.0,
) -> dict[str, str]:
    prob = float(sigmoid(logit))
    return {
        "game_id": str(game_id),
        "season": str(season),
        "week": str(week),
        "season_type": "regular",
        "kickoff_utc": f"{season}-09-0{min(week, 9)}T18:00:00+00:00",
        "home_team_id": "1",
        "away_team_id": "2",
        "home_team": "H",
        "away_team": "A",
        "home_win": str(y),
        "home_implied_prob": str(prob),
        "home_market_logit": str(logit),
        "home_conference": conference,
        "away_conference": "B",
        "home_classification": "fbs",
        "away_classification": "fbs",
        "neutral_site": "false",
        "home_field_advantage": "1",
        "is_week_1": "true" if week == 1 else "false",
        "is_weeks_1_3": "true" if week <= 3 else "false",
        "spread_home": "" if spread is None else str(spread),
        "total": "50",
        "home_moneyline": "-150",
        "away_moneyline": "130",
        "line_provider_count": "3",
        "spread_home_open": "",
        "total_open": "",
        "spread_move_home": "",
        "total_move": "",
        "home_entering_wins": "1",
        "home_entering_losses": "0",
        "away_entering_wins": "0",
        "away_entering_losses": "1",
        "home_previous_result": "1",
        "away_previous_result": "0",
        "home_sos": "0.5",
        "away_sos": "0.4",
        "home_days_rest": "7",
        "away_days_rest": "7",
        "sampling_frame": "all_fbs",
        "source_snapshot": "snap",
    }


def _write_matrix(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_market_only_matches_sigmoid(tmp_path: Path) -> None:
    rows = [
        _row(1, 2017, logit=-0.5, y=0),
        _row(2, 2017, logit=0.25, y=1),
        _row(3, 2018, logit=1.0, y=1),
        _row(4, 2018, logit=-1.0, y=0),
    ]
    matrix = tmp_path / "games_matrix_v1.csv"
    _write_matrix(matrix, rows)
    out = tmp_path / "out"
    fit_residual_walkforward(matrix, out)
    with (out / "predictions.csv").open() as handle:
        preds = [r for r in csv.DictReader(handle) if r["model"] == "market_only"]
    assert preds
    for pred in preds:
        logit = next(
            float(r["home_market_logit"])
            for r in rows
            if int(r["game_id"]) == int(pred["game_id"]) and int(r["season"]) == 2018
        )
        assert float(pred["p_home"]) == pytest.approx(float(sigmoid(logit)))


def test_baseline_inconsistency_raises(tmp_path: Path) -> None:
    rows = [_row(1, 2017, logit=0.0)]
    rows[0]["home_implied_prob"] = "0.9"
    with pytest.raises(ValueError, match="baseline inconsistency"):
        validate_baseline_consistency(rows)


def test_walkforward_writes_artifacts(tmp_path: Path) -> None:
    rows = [_row(i, 2017, logit=0.1 * i, y=i % 2) for i in range(1, 6)]
    rows += [_row(100 + i, 2018, logit=-0.2 * i, y=1 - (i % 2)) for i in range(1, 6)]
    matrix = tmp_path / "m.csv"
    _write_matrix(matrix, rows)
    out = tmp_path / "out"
    summary = fit_residual_walkforward(matrix, out)
    assert (out / "predictions.csv").exists()
    assert (out / "residual_details.csv").exists()
    assert (out / "summary.json").exists()
    assert (out / "run_manifest.json").exists()
    assert set(summary["variants"]) == set(VARIANTS)
    # one bundle per variant for test_2018
    bundles = list(out.glob("bundle_test_2018_*.json"))
    assert len(bundles) == len(VARIANTS)


def test_cli_fit_residual(tmp_path: Path) -> None:
    from pick_prophet.cli import main

    rows = [_row(i, 2017, y=1) for i in range(1, 4)]
    rows += [_row(10 + i, 2018, y=0) for i in range(1, 4)]
    matrix = tmp_path / "m.csv"
    _write_matrix(matrix, rows)
    out = tmp_path / "out"
    main(
        [
            "fit-residual",
            "--matrix",
            str(matrix),
            "--output-dir",
            str(out),
        ]
    )
    assert (out / "predictions.csv").exists()
