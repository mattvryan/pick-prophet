"""Paired walk-forward experiments for early-season games."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .folds import assert_train_precedes_test, expanding_folds
from .protocol import DEFAULT_PROTOCOL


def analyze_early_season(
    input_path: Path, output_dir: Path | None = None
) -> dict[str, Path]:
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    frame = pd.read_csv(input_path)
    frame = frame[
        frame.home_win.notna()
        & frame.spread_home.notna()
        & frame.elo_home.notna()
        & frame.elo_away.notna()
    ].copy()
    frame["elo_diff"] = frame.elo_home - frame.elo_away
    seasons = sorted(int(value) for value in frame.season.unique())
    folds = expanding_folds(seasons, DEFAULT_PROTOCOL)
    assert_train_precedes_test(folds)
    slices: dict[str, Callable[[Any], Any]] = {
        "week_1": lambda rows: rows.week == 1,
        "weeks_1_3": lambda rows: rows.week.between(1, 3),
        "weeks_4_plus": lambda rows: rows.week >= 4,
    }
    feature_sets = {
        "spread": ["spread_home"],
        "spread_plus_elo": ["spread_home", "elo_diff"],
    }

    predictions = []
    fold_rows = []
    for slice_name, selector in slices.items():
        for fold in folds:
            train = frame[frame.season.isin(fold.train_seasons) & selector(frame)]
            test = frame[(frame.season == fold.test_season) & selector(frame)]
            if train.empty or test.empty or train.home_win.nunique() < 2:
                continue
            fold_metrics: dict[str, Any] = {
                "slice": slice_name,
                "test_season": fold.test_season,
                "fold_id": fold.fold_id,
                "protocol_version": DEFAULT_PROTOCOL.protocol_version,
                "train_n": len(train),
                "test_n": len(test),
            }
            for model_name, columns in feature_sets.items():
                model = make_pipeline(
                    StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)
                )
                model.fit(train[columns], train.home_win.astype(int))
                probability = model.predict_proba(test[columns])[:, 1]
                y = test.home_win.astype(int)
                fold_metrics[model_name] = {
                    "accuracy": float(accuracy_score(y, probability >= 0.5)),
                    "log_loss": float(log_loss(y, probability, labels=[0, 1])),
                    "brier": float(brier_score_loss(y, probability)),
                }
                for position, (_index, row) in enumerate(test.iterrows()):
                    predictions.append(
                        {
                            "protocol_version": DEFAULT_PROTOCOL.protocol_version,
                            "slice": slice_name,
                            "test_season": fold.test_season,
                            "fold_id": fold.fold_id,
                            "game_id": int(row.game_id),
                            "week": int(row.week),
                            "home_win": int(row.home_win),
                            "model": model_name,
                            "home_probability": float(probability[position]),
                        }
                    )
            fold_metrics["delta_spread_plus_elo_minus_spread"] = {
                metric: fold_metrics["spread_plus_elo"][metric]
                - fold_metrics["spread"][metric]
                for metric in ("accuracy", "log_loss", "brier")
            }
            fold_rows.append(fold_metrics)

    summary: dict[str, Any] = {
        "input": str(input_path),
        "protocol_version": DEFAULT_PROTOCOL.protocol_version,
        "latest_oot_fold": DEFAULT_PROTOCOL.latest_oot_fold,
        "prospective_holdout": DEFAULT_PROTOCOL.prospective_holdout,
        "design": (
            "Expanding-window season folds under protocol 1.0.0. Within each "
            "slice, spread-only and spread-plus-Elo train and score on identical "
            "complete rows. 2025 is the latest in-loop OOT fold; 2026 weekly "
            "shadow is the prospective holdout."
        ),
        "slices": {},
        "folds": fold_rows,
    }
    for slice_name in slices:
        selected = [fold for fold in fold_rows if fold["slice"] == slice_name]
        total = sum(fold["test_n"] for fold in selected)
        aggregate: dict[str, Any] = {
            "folds": len(selected),
            "test_n": total,
            "models": {},
        }
        if not total:
            aggregate["status"] = "insufficient_data"
            summary["slices"][slice_name] = aggregate
            continue
        for model_name in feature_sets:
            aggregate["models"][model_name] = {
                metric: sum(
                    fold[model_name][metric] * fold["test_n"] for fold in selected
                )
                / total
                for metric in ("accuracy", "log_loss", "brier")
            }
        aggregate["delta_spread_plus_elo_minus_spread"] = {
            metric: aggregate["models"]["spread_plus_elo"][metric]
            - aggregate["models"]["spread"][metric]
            for metric in ("accuracy", "log_loss", "brier")
        }
        aggregate["elo_improved_fold_count"] = {
            metric: sum(
                fold["delta_spread_plus_elo_minus_spread"][metric] < 0
                for fold in selected
            )
            for metric in ("log_loss", "brier")
        }
        summary["slices"][slice_name] = aggregate

    output_dir = output_dir or input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "early_season_analysis.json"
    predictions_path = output_dir / "early_season_predictions.csv"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    pd.DataFrame(predictions).to_csv(predictions_path, index=False)
    return {"summary": summary_path, "predictions": predictions_path}
