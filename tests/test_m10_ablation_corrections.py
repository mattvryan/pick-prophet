"""Regression tests for M10 ablation corrections."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from pick_prophet.models.fixed_offset_logit import predict_raw
from pick_prophet.models.residual_ablation import run_ablation, season_drop_metrics
from pick_prophet.models.residual_ablation_variants import (
    UNAVAILABLE_FOR_EVIDENCE,
    build_ablation_variants,
)
from pick_prophet.models.residual_fit import fit_residual_walkforward
from pick_prophet.models.residual_preprocess import (
    BOOLEAN_COLUMNS,
    FoldPreprocessor,
    _as_float,
)


def test_boolean_csv_true_false_parsed_as_one_zero() -> None:
    assert _as_float("true", boolean=True) == 1.0
    assert _as_float("false", boolean=True) == 0.0
    assert _as_float("TRUE", boolean=True) == 1.0
    assert "is_week_1" in BOOLEAN_COLUMNS
    train = [
        {"is_week_1": "true", "home_field_advantage": "false"},
        {"is_week_1": "false", "home_field_advantage": "true"},
    ]
    prep = FoldPreprocessor(("is_week_1", "home_field_advantage")).fit(train)
    assert "is_week_1" in prep.feature_names_
    assert prep.unavailable_source_columns_ == []
    x = prep.transform([{"is_week_1": "true", "home_field_advantage": "false"}])
    # scaled values finite; missing indicators 0
    assert x.shape[1] == 4
    assert x[0, 1] == 0.0
    assert x[0, 3] == 0.0


def test_all_missing_feature_emits_no_columns_and_matches_market() -> None:
    train = [{"spread_home_open": None}, {"spread_home_open": ""}]
    test = [{"spread_home_open": None, "home_market_logit": 0.5}]
    prep = FoldPreprocessor(("spread_home_open",)).fit(train)
    assert prep.feature_names_ == []
    assert prep.unavailable_source_columns_ == ["spread_home_open"]
    x = prep.transform(test)
    assert x.shape == (1, 0)
    offsets = np.array([0.5])
    beta = np.zeros(0)
    p = predict_raw(offsets, x, beta)
    np.testing.assert_allclose(p, predict_raw(offsets, np.zeros((1, 0)), np.zeros(0)))


def test_structurally_unavailable_excluded_from_variants() -> None:
    variants = build_ablation_variants()
    for col in UNAVAILABLE_FOR_EVIDENCE:
        assert f"single__{col}" not in variants
        for name, columns in variants.items():
            assert col not in columns, name


def test_anomalous_season_drop_still_ok_for_present_seasons() -> None:
    paired = [
        {
            "test_season": 2022,
            "y_true": 1,
            "p_candidate": 0.7,
            "p_market": 0.6,
        },
        {
            "test_season": 2023,
            "y_true": 0,
            "p_candidate": 0.4,
            "p_market": 0.5,
        },
    ]
    assert season_drop_metrics(paired, drop_season=2022)["status"] == "ok"


def test_anomalous_not_available_in_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pick_prophet.models.residual_ablation as abl

    monkeypatch.setattr(abl, "assert_ablation_variants_valid", lambda variants=None: None)

    # Minimal matrix with seasons 2021 train + 2022 test only (no 2020 held-out)
    from pick_prophet.models.fixed_offset_logit import sigmoid

    def row(gid: int, season: int, y: int, logit: float) -> dict[str, str]:
        p = sigmoid(logit)
        return {
            "game_id": str(gid),
            "season": str(season),
            "week": "2",
            "season_type": "regular",
            "kickoff_utc": f"{season}-09-01T18:00:00+00:00",
            "home_team_id": "1",
            "away_team_id": "2",
            "home_team": "H",
            "away_team": "A",
            "home_win": str(y),
            "home_implied_prob": str(p),
            "home_market_logit": str(logit),
            "home_conference": "A",
            "away_conference": "B",
            "home_classification": "fbs",
            "away_classification": "fbs",
            "neutral_site": "false",
            "home_field_advantage": "true",
            "is_week_1": "false",
            "is_weeks_1_3": "true",
            "spread_home": "-3",
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

    rows = []
    gid = 1
    for season in (2021, 2022):
        for i in range(6):
            rows.append(row(gid, season, i % 2, 0.1 if i % 2 == 0 else -0.1))
            gid += 1
    matrix = tmp_path / "m.csv"
    with matrix.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    variants = {
        "market_only": (),
        "single__home_field_advantage": ("home_field_advantage",),
    }
    paths = run_ablation(
        matrix,
        tmp_path / "out",
        variants=variants,
        n_boot=10,
        enforce_protocol_n_boot=False,
    )
    anom = list(csv.DictReader(paths["anomalous_season"].open()))
    assert anom
    assert all(r["status"] == "not_available" for r in anom)
    assert all(r["delta_log_loss"] == "" for r in anom)
    assert all(r["reason"] == "no_held_out_predictions_for_anomalous_season" for r in anom)


def test_protocol_n_boot_enforced(tmp_path: Path) -> None:
    matrix = tmp_path / "m.csv"
    matrix.write_text("game_id,season\n1,2022\n")
    with pytest.raises(ValueError, match="n_boot"):
        run_ablation(
            matrix,
            tmp_path / "out",
            n_boot=200,
            enforce_protocol_n_boot=True,
        )


def test_boolean_fit_does_not_treat_true_as_missing(tmp_path: Path) -> None:
    """Walk-forward with boolean CSV strings should fit non-empty design."""

    from pick_prophet.models.fixed_offset_logit import sigmoid

    rows = []
    gid = 1
    for season in (2021, 2022):
        for week, flag in ((1, "true"), (2, "false"), (3, "true"), (4, "false")):
            logit = 0.2 if flag == "true" else -0.2
            y = 1 if flag == "true" else 0
            p = sigmoid(logit)
            rows.append(
                {
                    "game_id": str(gid),
                    "season": str(season),
                    "week": str(week),
                    "season_type": "regular",
                    "kickoff_utc": f"{season}-09-0{week}T18:00:00+00:00",
                    "home_team_id": "1",
                    "away_team_id": "2",
                    "home_team": "H",
                    "away_team": "A",
                    "home_win": str(y),
                    "home_implied_prob": str(p),
                    "home_market_logit": str(logit),
                    "home_conference": "A",
                    "away_conference": "B",
                    "home_classification": "fbs",
                    "away_classification": "fbs",
                    "neutral_site": "false",
                    "home_field_advantage": "true",
                    "is_week_1": flag if week == 1 else "false",
                    "is_weeks_1_3": "true" if week <= 3 else "false",
                    "spread_home": "-3",
                    "total": "50",
                    "home_moneyline": "-150",
                    "away_moneyline": "130",
                    "line_provider_count": "2",
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
            )
            gid += 1
    path = tmp_path / "m.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = fit_residual_walkforward(
        path,
        tmp_path / "fit",
        variants={
            "market_only": (),
            "single__is_week_1": ("is_week_1",),
        },
    )
    assert summary["folds"]
    # Bundle should have a coefficient for the boolean feature (not empty unavailable)
    import json

    bundle = json.loads(
        next((tmp_path / "fit").glob("bundle_*_single__is_week_1.json")).read_text()
    )
    assert bundle["feature_names"]
    assert "is_week_1" in bundle["feature_names"]
