"""Tests for M09 residual diagnostics."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import pytest

from pick_prophet.cli import parser
from pick_prophet.models.residual_diagnostics import (
    diagnose_residual,
    fit_calibration_glm,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_mini_run(tmp: Path) -> tuple[Path, Path]:
    """Two seasons, two weeks, market_only + combined; all_fbs == overall."""

    matrix_path = tmp / "matrix.csv"
    matrix_rows = []
    for season, week, gid, y, spread, neutral in [
        (2018, 1, 1, 1, -2.0, False),
        (2018, 1, 2, 0, -10.0, False),
        (2018, 2, 3, 1, -5.0, True),
        (2019, 1, 4, 0, -1.0, False),
        (2019, 2, 5, 1, None, False),
        (2019, 2, 6, 0, -4.0, False),
    ]:
        matrix_rows.append(
            {
                "game_id": gid,
                "season": season,
                "week": week,
                "season_type": "regular",
                "neutral_site": str(neutral),
                "spread_home": "" if spread is None else spread,
            }
        )
    _write_csv(
        matrix_path,
        matrix_rows,
        ["game_id", "season", "week", "season_type", "neutral_site", "spread_home"],
    )

    pred_rows = []
    detail_rows = []
    # Market probs and candidate adjustments
    specs = [
        # gid, season, week, fold, y, p_mkt, adj
        (1, 2018, 1, "fold_2018", 1, 0.55, 0.20),
        (2, 2018, 1, "fold_2018", 0, 0.70, -0.10),
        (3, 2018, 2, "fold_2018", 1, 0.60, 0.40),
        (4, 2019, 1, "fold_2019", 0, 0.52, 0.02),
        (5, 2019, 2, "fold_2019", 1, 0.50, 0.0),  # market tie
        (6, 2019, 2, "fold_2019", 0, 0.65, -0.25),
    ]

    def sigmoid(z: float) -> float:
        return 1.0 / (1.0 + math.exp(-z))

    for gid, season, week, fold, y, p_mkt, adj in specs:
        logit = math.log(p_mkt / (1 - p_mkt))
        p_cand = sigmoid(logit + adj)
        for model, p, adjustment in (
            ("market_only", p_mkt, 0.0),
            ("combined", p_cand, adj),
        ):
            pred_rows.append(
                {
                    "protocol_version": "1.0.0",
                    "model": model,
                    "fold_id": fold,
                    "test_season": season,
                    "game_id": gid,
                    "week": week,
                    "y_true": y,
                    "p_home": p,
                    "sampling_frame": "all_fbs",
                }
            )
            detail_rows.append(
                {
                    "model": model,
                    "fold_id": fold,
                    "test_season": season,
                    "game_id": gid,
                    "matrix_schema_version": "1.0.0",
                    "p_home": p,
                    "p_home_scored": p,
                    "market_logit": logit,
                    "adjustment": adjustment,
                }
            )

    run = tmp / "residual"
    run.mkdir()
    pred_path = run / "predictions.csv"
    detail_path = run / "residual_details.csv"
    elig_path = run / "eligibility.csv"
    summary_path = run / "summary.json"
    _write_csv(
        pred_path,
        pred_rows,
        [
            "protocol_version",
            "model",
            "fold_id",
            "test_season",
            "game_id",
            "week",
            "y_true",
            "p_home",
            "sampling_frame",
        ],
    )
    _write_csv(
        detail_path,
        detail_rows,
        [
            "model",
            "fold_id",
            "test_season",
            "game_id",
            "matrix_schema_version",
            "p_home",
            "p_home_scored",
            "market_logit",
            "adjustment",
        ],
    )
    _write_csv(
        elig_path,
        [
            {
                "fold_id": "fold_2018",
                "split": "test",
                "game_id": "",
                "reason_code": "eligible",
                "input_rows": 3,
                "eligible_rows": 3,
                "excluded_rows": 0,
            }
        ],
        [
            "fold_id",
            "split",
            "game_id",
            "reason_code",
            "input_rows",
            "eligible_rows",
            "excluded_rows",
        ],
    )
    summary_path.write_text("{}\n")
    manifest = {
        "bundle_hashes": {},
        "eligibility_sha256": _sha(elig_path),
        "matrix_path": str(matrix_path),
        "matrix_schema_version": "1.0.0",
        "matrix_sha256": _sha(matrix_path),
        "predictions_sha256": _sha(pred_path),
        "protocol_version": "1.0.0",
        "residual_details_sha256": _sha(detail_path),
        "summary_sha256": _sha(summary_path),
        "variants": ["market_only", "combined"],
    }
    (run / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return run, matrix_path


def test_diagnose_residual_smoke(tmp_path: Path) -> None:
    run, matrix = _build_mini_run(tmp_path)
    out = tmp_path / "diag"
    paths = diagnose_residual(run, matrix, out, n_boot=25)
    required = [
        "summary",
        "overall_metrics",
        "paired_bootstrap",
        "slice_metrics",
        "reliability_bins",
        "calibration_fit",
        "adjustment_bands",
        "flip_summary",
        "fold_consistency",
        "exclusions",
        "report",
    ]
    for key in required:
        assert paths[key].is_file(), key
    summary = json.loads(paths["summary"].read_text())
    assert summary["raw_predictions_unchanged"] is True
    assert summary["calibrated_candidate"] is False
    report = paths["report"].read_text()
    assert "raw" in report.lower()
    assert "calibrated prediction candidate" in report.lower()

    flips = list(csv.DictReader(paths["flip_summary"].open()))
    assert int(flips[0]["market_tie"]) + int(flips[0]["candidate_tie"]) >= 1

    slices = list(csv.DictReader(paths["slice_metrics"].open()))
    overall = [r for r in slices if r["slice"] == "overall" and r["variant"] == "combined"]
    all_fbs = [r for r in slices if r["slice"] == "all_fbs" and r["variant"] == "combined"]
    assert overall and all_fbs
    # Identical populations: one keeps p, the other is deduped
    reasons = {overall[0]["reason"], all_fbs[0]["reason"]}
    assert "duplicate_population" in reasons


def test_hash_mismatch_fails(tmp_path: Path) -> None:
    run, matrix = _build_mini_run(tmp_path)
    manifest = json.loads((run / "run_manifest.json").read_text())
    manifest["predictions_sha256"] = "0" * 64
    (run / "run_manifest.json").write_text(json.dumps(manifest) + "\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        diagnose_residual(run, matrix, tmp_path / "out", n_boot=5)


def test_unequal_ids_fail(tmp_path: Path) -> None:
    run, matrix = _build_mini_run(tmp_path)
    preds = list(csv.DictReader((run / "predictions.csv").open()))
    preds = [r for r in preds if not (r["model"] == "combined" and r["game_id"] == "6")]
    fieldnames = list(preds[0].keys())
    _write_csv(run / "predictions.csv", preds, fieldnames)
    details = list(csv.DictReader((run / "residual_details.csv").open()))
    details = [r for r in details if not (r["model"] == "combined" and r["game_id"] == "6")]
    _write_csv(run / "residual_details.csv", details, list(details[0].keys()))
    # refresh hashes
    summary_path = run / "summary.json"
    manifest = {
        "eligibility_sha256": _sha(run / "eligibility.csv"),
        "matrix_sha256": _sha(matrix),
        "predictions_sha256": _sha(run / "predictions.csv"),
        "residual_details_sha256": _sha(run / "residual_details.csv"),
        "summary_sha256": _sha(summary_path),
    }
    (run / "run_manifest.json").write_text(json.dumps(manifest) + "\n")
    with pytest.raises(ValueError, match="unequal paired"):
        diagnose_residual(run, matrix, tmp_path / "out", n_boot=5)


def test_invalid_probability_rejected(tmp_path: Path) -> None:
    run, matrix = _build_mini_run(tmp_path)
    preds = list(csv.DictReader((run / "predictions.csv").open()))
    for row in preds:
        if row["model"] == "combined" and row["game_id"] == "1":
            row["p_home"] = "1.5"
    _write_csv(run / "predictions.csv", preds, list(preds[0].keys()))
    details = list(csv.DictReader((run / "residual_details.csv").open()))
    for row in details:
        if row["model"] == "combined" and row["game_id"] == "1":
            row["p_home"] = "1.5"
    _write_csv(run / "residual_details.csv", details, list(details[0].keys()))
    summary_path = run / "summary.json"
    manifest = {
        "eligibility_sha256": _sha(run / "eligibility.csv"),
        "matrix_sha256": _sha(matrix),
        "predictions_sha256": _sha(run / "predictions.csv"),
        "residual_details_sha256": _sha(run / "residual_details.csv"),
        "summary_sha256": _sha(summary_path),
    }
    (run / "run_manifest.json").write_text(json.dumps(manifest) + "\n")
    with pytest.raises(ValueError, match="out of \\[0,1\\]"):
        diagnose_residual(run, matrix, tmp_path / "out", n_boot=5)


def test_calibration_single_class_status() -> None:
    out = fit_calibration_glm([1, 1, 1], [0.2, 0.5, 0.8])
    assert out["status"] == "not_estimable"
    assert out["reason"] == "single_class"
    assert out["a"] is None


def test_calibration_near_zero_one_does_not_mutate_inputs() -> None:
    y = [0, 1, 0, 1]
    p = [1e-12, 1 - 1e-12, 0.4, 0.6]
    original = list(p)
    out = fit_calibration_glm(y, p)
    assert p == original
    assert out["status"] in {"ok", "not_estimable", "failed"}


def test_flip_boundary_tolerance() -> None:
    from pick_prophet.models.residual_diagnostics import _classify_side

    assert _classify_side(0.5) == "tie"
    assert _classify_side(0.5 + 1e-13) == "tie"
    assert _classify_side(0.5 + 1e-11) == "home"
    assert _classify_side(0.5 - 1e-11) == "away"


def test_cli_diagnose_residual(tmp_path: Path) -> None:
    run, matrix = _build_mini_run(tmp_path)
    out = tmp_path / "cli_out"
    args = parser().parse_args(
        [
            "diagnose-residual",
            "--predictions-dir",
            str(run),
            "--matrix",
            str(matrix),
            "--out-dir",
            str(out),
        ]
    )
    # Call diagnose directly with small n_boot; CLI uses protocol default.
    # Smoke the argparse wiring here.
    assert args.command == "diagnose-residual"
    paths = diagnose_residual(run, matrix, out, n_boot=10)
    assert (out / "report.md").is_file()
    assert paths["summary"].is_file()
