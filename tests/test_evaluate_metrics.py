"""Tests for calibration, bootstrap determinism, and evaluate artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pick_prophet.evaluation.artifacts import PREDICTION_COLUMNS, sampling_frame_for_row
from pick_prophet.evaluation.evaluate import evaluate
from pick_prophet.evaluation.metrics import bootstrap_paired_delta, calibration_bins
from pick_prophet.evaluation.protocol import ProtocolConfig


def test_calibration_bins_cover_unit_interval() -> None:
    y = [0, 1, 1, 0, 1, 0, 1, 0, 1, 0]
    p = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
    bins = calibration_bins(y, p, n_bins=10)
    assert len(bins) == 10
    assert bins[0]["count"] == 1
    assert bins[9]["lo"] == pytest.approx(0.9)


def test_bootstrap_is_deterministic_for_fixed_seed() -> None:
    weeks = [1, 1, 2, 2, 3, 3]
    y = [1, 0, 1, 0, 1, 0]
    left = [0.6, 0.4, 0.7, 0.3, 0.55, 0.45]
    right = [0.65, 0.35, 0.75, 0.25, 0.6, 0.4]
    a = bootstrap_paired_delta(
        weeks, y, left, right, metric="log_loss", n_boot=100, seed=20260904
    )
    b = bootstrap_paired_delta(
        weeks, y, left, right, metric="log_loss", n_boot=100, seed=20260904
    )
    assert a == b


def test_sampling_frame_requires_confirmed_pickem() -> None:
    assert sampling_frame_for_row({"is_pickem_game": True}) == "all_fbs"
    assert (
        sampling_frame_for_row(
            {"is_pickem_game": True, "verification_status": "confirmed"}
        )
        == "verified_espn_pickem"
    )


def test_evaluate_writes_protocol_stamped_artifacts(tmp_path: Path) -> None:
    rows = []
    game_id = 1
    for season in (2023, 2024, 2025):
        for week in (1, 2):
            for home_win in (0, 1, 0, 1, 1, 0):
                rows.append(
                    {
                        "game_id": game_id,
                        "season": season,
                        "week": week,
                        "home_win": home_win,
                        "spread_home": -3 if home_win else 4,
                        "elo_home": 1510 if home_win else 1490,
                        "elo_away": 1500,
                        "fpi_home": None,
                        "fpi_away": None,
                        "sp_home": None,
                        "sp_away": None,
                        "neutral_site": False,
                    }
                )
                game_id += 1
    source = tmp_path / "games.csv"
    pd.DataFrame(rows).to_csv(source, index=False)
    # Use a tiny bootstrap for speed while keeping the protocol seed.
    artifacts = evaluate(
        source,
        tmp_path / "out",
        protocol=ProtocolConfig(n_boot=20),
    )
    summary = json.loads(artifacts["summary"].read_text())
    assert summary["protocol_version"] == "1.0.0"
    assert summary["latest_oot_fold"] == 2025
    assert summary["prospective_holdout"] == "2026_weekly_shadow"
    assert [f["test_season"] for f in summary["folds"]] == [2024, 2025]
    predictions = pd.read_csv(artifacts["predictions"])
    for column in PREDICTION_COLUMNS:
        assert column in predictions.columns
    assert set(predictions.protocol_version.unique()) == {"1.0.0"}
