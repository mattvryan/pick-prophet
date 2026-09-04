"""Protocol-stamped walk-forward evaluation runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import (
    iter_prediction_rows,
    sampling_frame_for_row,
    write_predictions,
    write_summary,
)
from .folds import assert_train_precedes_test, expanding_folds, pair_game_ids
from .metrics import bootstrap_paired_delta, calibration_bins, score_probabilities
from .protocol import ProtocolConfig, load_protocol


def _favorite_band(spread: Any) -> str:
    import math

    if spread is None:
        return "missing_spread"
    try:
        magnitude = abs(float(spread))
    except (TypeError, ValueError):
        return "missing_spread"
    if math.isnan(magnitude):
        return "missing_spread"
    if magnitude < 3:
        return "lt_3"
    if magnitude <= 7:
        return "3_to_7"
    return "gt_7"


def _slice_mask(frame: Any, name: str) -> Any:
    if name == "week_1":
        return frame.week == 1
    if name == "weeks_1_3":
        return frame.week.between(1, 3)
    if name == "weeks_4_plus":
        return frame.week >= 4
    if name == "neutral_site":
        return frame.neutral_site.astype(str).str.lower().isin(["true", "1"])
    if name == "favorite_lt_3":
        return frame["_favorite_band"] == "lt_3"
    if name == "favorite_3_to_7":
        return frame["_favorite_band"] == "3_to_7"
    if name == "favorite_gt_7":
        return frame["_favorite_band"] == "gt_7"
    if name == "missing_spread":
        return frame["_favorite_band"] == "missing_spread"
    if name == "all_fbs":
        return frame["_sampling_frame"] == "all_fbs"
    if name == "verified_espn_pickem":
        return frame["_sampling_frame"] == "verified_espn_pickem"
    raise ValueError(f"unknown slice {name!r}")


def evaluate(
    input_path: Path,
    output_dir: Path | None = None,
    *,
    protocol: ProtocolConfig | None = None,
    protocol_version: str | None = None,
) -> dict[str, Path]:
    """Run protocol walk-forward baselines and write stamped artifacts."""

    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    protocol = protocol or load_protocol(protocol_version)
    frame = pd.read_csv(input_path)
    frame = frame[frame.home_win.notna()].copy()
    if "week" not in frame.columns:
        frame["week"] = 0
    if "neutral_site" not in frame.columns:
        frame["neutral_site"] = False
    if "game_id" not in frame.columns:
        frame["game_id"] = range(1, len(frame) + 1)
    if "elo_home" in frame.columns and "elo_away" in frame.columns:
        frame["elo_diff"] = frame.elo_home - frame.elo_away
    else:
        frame["elo_diff"] = None
    if "fpi_home" in frame.columns and "fpi_away" in frame.columns:
        frame["fpi_diff"] = frame.fpi_home - frame.fpi_away
    else:
        frame["fpi_diff"] = None
    if "sp_home" in frame.columns and "sp_away" in frame.columns:
        frame["sp_diff"] = frame.sp_home - frame.sp_away
    else:
        frame["sp_diff"] = None
    if "spread_home" in frame.columns:
        frame["_favorite_band"] = frame.spread_home.map(_favorite_band)
    else:
        frame["_favorite_band"] = "missing_spread"
    frame["_sampling_frame"] = [
        sampling_frame_for_row(row) for _, row in frame.iterrows()
    ]

    seasons = sorted(int(value) for value in frame.season.unique())
    folds = expanding_folds(seasons, protocol)
    assert_train_precedes_test(folds)

    candidates = {
        "spread_logistic": ["spread_home"],
        "elo_logistic": ["elo_diff"],
        "spread_plus_elo_logistic": ["spread_home", "elo_diff"],
        "fpi_logistic": ["fpi_diff"],
        "sp_plus_logistic": ["sp_diff"],
    }

    prediction_rows: list[dict[str, Any]] = []
    walk_forward: dict[str, Any] = {}
    for name, columns in candidates.items():
        model_folds = []
        skipped = []
        for fold in folds:
            train = frame[frame.season.isin(fold.train_seasons)].dropna(subset=columns)
            test = frame[frame.season == fold.test_season].dropna(subset=columns)
            if train.empty or test.empty:
                skipped.append(
                    {
                        "season": fold.test_season,
                        "fold_id": fold.fold_id,
                        "reason": "no complete training rows"
                        if train.empty
                        else "no complete test rows",
                        "train_n": len(train),
                        "test_n": len(test),
                    }
                )
                continue
            if train.home_win.nunique() < 2:
                skipped.append(
                    {
                        "season": fold.test_season,
                        "fold_id": fold.fold_id,
                        "reason": "training target has fewer than two classes",
                        "train_n": len(train),
                        "test_n": len(test),
                    }
                )
                continue
            model = make_pipeline(
                StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)
            )
            model.fit(train[columns], train.home_win.astype(int))
            probabilities = model.predict_proba(test[columns])[:, 1]
            y = test.home_win.astype(int).tolist()
            p = [float(value) for value in probabilities]
            metrics = score_probabilities(y, p)
            metrics["coverage"] = float(len(test)) / float(
                len(frame[frame.season == fold.test_season])
            )
            metrics["calibration"] = calibration_bins(
                y, p, n_bins=protocol.calibration_bins
            )
            slice_metrics: dict[str, Any] = {}
            for slice_name in protocol.required_slices:
                mask = _slice_mask(test, slice_name)
                subset = test[mask]
                if subset.empty:
                    slice_metrics[slice_name] = {"n": 0, "status": "empty"}
                    continue
                # Align probabilities to subset via positional index in test
                positions = [test.index.get_loc(idx) for idx in subset.index]
                if any(isinstance(pos, slice) for pos in positions):
                    slice_metrics[slice_name] = {
                        "n": len(subset),
                        "status": "duplicate_index",
                    }
                    continue
                slice_p = [p[i] for i in positions]
                slice_y = subset.home_win.astype(int).tolist()
                slice_metrics[slice_name] = score_probabilities(slice_y, slice_p)
            model_folds.append(
                {
                    "season": fold.test_season,
                    "fold_id": fold.fold_id,
                    "train_n": len(train),
                    "train_seasons": list(fold.train_seasons),
                    **{k: metrics[k] for k in ("n", "accuracy", "log_loss", "brier")},
                    "coverage": metrics["coverage"],
                    "calibration": metrics["calibration"],
                    "slices": slice_metrics,
                }
            )
            frames = [sampling_frame_for_row(row) for _, row in test.iterrows()]
            prediction_rows.extend(
                iter_prediction_rows(
                    protocol_version=protocol.protocol_version,
                    model=name,
                    fold_id=fold.fold_id,
                    test_season=fold.test_season,
                    game_ids=test.game_id.tolist(),
                    weeks=test.week.tolist(),
                    y_true=y,
                    p_home=p,
                    sampling_frames=frames,
                )
            )
        walk_forward[name] = {
            "features": columns,
            "folds": model_folds,
            "skipped_folds": skipped,
        }

    # Paired delta vs spread baseline on latest overlapping fold when possible.
    paired: dict[str, Any] = {}
    baseline_name = "spread_logistic"
    for name in walk_forward:
        if name == baseline_name:
            continue
        try:
            # Use predictions from the latest OOT season when both models scored it.
            base_rows = [
                row
                for row in prediction_rows
                if row["model"] == baseline_name
                and row["test_season"] == protocol.latest_oot_fold
            ]
            cand_rows = [
                row
                for row in prediction_rows
                if row["model"] == name
                and row["test_season"] == protocol.latest_oot_fold
            ]
            if not base_rows or not cand_rows:
                paired[name] = {"status": "skipped", "reason": "missing latest OOT rows"}
                continue
            ids = pair_game_ids(
                (row["game_id"] for row in base_rows),
                (row["game_id"] for row in cand_rows),
                context=f"{name} vs {baseline_name}",
            )
            base_by_id = {row["game_id"]: row for row in base_rows}
            cand_by_id = {row["game_id"]: row for row in cand_rows}
            ordered = list(ids)
            weeks = [base_by_id[i]["week"] for i in ordered]
            y = [base_by_id[i]["y_true"] for i in ordered]
            p_base = [base_by_id[i]["p_home"] for i in ordered]
            p_cand = [cand_by_id[i]["p_home"] for i in ordered]
            paired[name] = {
                "baseline": baseline_name,
                "test_season": protocol.latest_oot_fold,
                "n": len(ordered),
                "log_loss": bootstrap_paired_delta(
                    weeks,
                    y,
                    p_base,
                    p_cand,
                    metric="log_loss",
                    n_boot=protocol.n_boot,
                    seed=protocol.bootstrap_seed,
                ),
                "brier": bootstrap_paired_delta(
                    weeks,
                    y,
                    p_base,
                    p_cand,
                    metric="brier",
                    n_boot=protocol.n_boot,
                    seed=protocol.bootstrap_seed,
                ),
            }
        except ValueError as exc:
            paired[name] = {"status": "rejected", "reason": str(exc)}

    summary = {
        "input": str(input_path),
        "protocol": protocol.to_dict(),
        "protocol_version": protocol.protocol_version,
        "seasons": seasons,
        "folds": [
            {
                "fold_id": fold.fold_id,
                "test_season": fold.test_season,
                "train_seasons": list(fold.train_seasons),
            }
            for fold in folds
        ],
        "latest_oot_fold": protocol.latest_oot_fold,
        "prospective_holdout": protocol.prospective_holdout,
        "sampling_frame": (
            "all games involving at least one FBS team; verified ESPN Pick'em "
            "reported separately when confirmation flags exist"
        ),
        "walk_forward_models": walk_forward,
        "paired_vs_spread_logistic": paired,
        "pickem_status": (
            "verified_espn_pickem unavailable"
            if not (frame["_sampling_frame"] == "verified_espn_pickem").any()
            else "verified_espn_pickem rows present"
        ),
    }

    output_dir = output_dir or input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = write_summary(summary, output_dir / "evaluation_summary.json")
    predictions_path = write_predictions(
        prediction_rows,
        output_dir / "evaluation_predictions.csv",
        protocol_version=protocol.protocol_version,
    )
    return {"summary": summary_path, "predictions": predictions_path}
