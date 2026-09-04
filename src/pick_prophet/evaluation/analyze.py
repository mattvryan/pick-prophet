"""Leakage-aware descriptive and walk-forward historical baselines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .folds import assert_train_precedes_test, expanding_folds
from .protocol import DEFAULT_PROTOCOL


def analyze_file(input_path: Path, output_path: Path | None = None) -> Path:
    try:
        import pandas as pd
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError(
            "analysis dependencies missing; run pip install -e '.[dev]'"
        ) from exc

    frame = pd.read_csv(input_path)
    frame = frame[frame.home_win.notna()].copy()
    frame["elo_diff"] = frame.elo_home - frame.elo_away
    frame["fpi_diff"] = frame.fpi_home - frame.fpi_away
    frame["sp_diff"] = frame.sp_home - frame.sp_away
    seasons = sorted(int(value) for value in frame.season.unique())
    folds = expanding_folds(seasons, DEFAULT_PROTOCOL)
    assert_train_precedes_test(folds)

    def probability_metrics(rows: Any, probabilities: Any) -> dict[str, Any]:
        y = rows.home_win.astype(int)
        return {
            "n": len(rows),
            "accuracy": float(accuracy_score(y, probabilities >= 0.5)),
            "log_loss": float(log_loss(y, probabilities, labels=[0, 1])),
            "brier": float(brier_score_loss(y, probabilities)),
        }

    results: dict[str, Any] = {
        "input": str(input_path),
        "protocol_version": DEFAULT_PROTOCOL.protocol_version,
        "latest_oot_fold": DEFAULT_PROTOCOL.latest_oot_fold,
        "prospective_holdout": DEFAULT_PROTOCOL.prospective_holdout,
        "seasons": seasons,
        "rows": len(frame),
        "sampling_frame": "all games involving at least one FBS team; not confirmed ESPN slates",
        "line_timing": (
            "CFBD historical provider values are treated as final/closing-like snapshots; "
            "provider observation timestamps are unavailable"
        ),
        "coverage_by_season": {},
        "direct_baselines": {},
        "walk_forward_models": {},
    }
    coverage_columns = [
        "spread_home",
        "home_implied_prob",
        "elo_diff",
        "fpi_diff",
        "sp_diff",
    ]
    for season in seasons:
        rows = frame[frame.season == season]
        results["coverage_by_season"][str(season)] = {
            "rows": len(rows),
            **{
                column: float(rows[column].notna().mean())
                for column in coverage_columns
            },
        }

    moneyline_folds = []
    spread_folds = []
    for season in seasons:
        rows = frame[frame.season == season]
        moneyline = rows.dropna(subset=["home_implied_prob"])
        if len(moneyline):
            moneyline_folds.append(
                {
                    "season": season,
                    **probability_metrics(moneyline, moneyline.home_implied_prob),
                }
            )
        spread = rows.dropna(subset=["spread_home"])
        spread = spread[spread.spread_home != 0]
        if len(spread):
            spread_folds.append(
                {
                    "season": season,
                    "n": len(spread),
                    "accuracy": float(
                        accuracy_score(
                            spread.home_win.astype(int), spread.spread_home < 0
                        )
                    ),
                }
            )
    results["direct_baselines"] = {
        "vig_removed_moneyline": moneyline_folds,
        "spread_favorite": spread_folds,
    }

    candidates = {
        "spread_logistic": ["spread_home"],
        "elo_logistic": ["elo_diff"],
        "spread_plus_elo_logistic": ["spread_home", "elo_diff"],
        "fpi_logistic": ["fpi_diff"],
        "sp_plus_logistic": ["sp_diff"],
    }
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
            model_folds.append(
                {
                    "season": fold.test_season,
                    "fold_id": fold.fold_id,
                    "train_n": len(train),
                    **probability_metrics(test, probabilities),
                }
            )
        results["walk_forward_models"][name] = {
            "features": columns,
            "folds": model_folds,
            "skipped_folds": skipped,
        }

    output_path = output_path or input_path.with_suffix(".analysis.json")
    output_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return output_path
