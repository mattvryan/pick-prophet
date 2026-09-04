"""Baseline and walk-forward analysis entry points."""

from __future__ import annotations

import json
from pathlib import Path


def analyze_file(input_path: Path, output_path: Path | None = None) -> Path:
    try:
        import pandas as pd
        from sklearn.compose import ColumnTransformer
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError("analysis dependencies missing; run pip install -e '.[dev]'") from exc

    frame = pd.read_csv(input_path)
    frame = frame[frame.home_win.notna()].copy()
    frame["fpi_diff"] = frame.fpi_home - frame.fpi_away
    frame["sp_diff"] = frame.sp_home - frame.sp_away
    frame["elo_diff"] = frame.elo_home - frame.elo_away
    candidates = {
        "market_moneyline": ["home_implied_prob"],
        "spread": ["spread_home"],
        "fpi": ["fpi_diff"],
        "sp_plus": ["sp_diff"],
        "elo": ["elo_diff"],
        "market_plus_fpi": ["spread_home", "fpi_diff"],
        "market_plus_sp": ["spread_home", "sp_diff"],
    }
    results: dict[str, object] = {
        "input": str(input_path),
        "rows": len(frame),
        "warning": None,
        "models": {},
    }
    seasons = sorted(frame.season.unique())
    if len(seasons) < 2:
        results["warning"] = (
            "At least two seasons are required for walk-forward model evaluation. "
            "Only descriptive coverage and the direct market baseline are reported."
        )

    direct = frame.dropna(subset=["home_implied_prob"])
    if len(direct):
        y, p = direct.home_win.astype(int), direct.home_implied_prob
        results["models"]["market_direct"] = {
            "n": len(direct),
            "accuracy": accuracy_score(y, p >= 0.5),
            "log_loss": log_loss(y, p, labels=[0, 1]),
            "brier": brier_score_loss(y, p),
        }

    for name, columns in candidates.items():
        folds = []
        for test_season in seasons[1:]:
            train = frame[frame.season < test_season]
            test = frame[frame.season == test_season]
            if train.home_win.nunique() < 2 or test.empty:
                continue
            model = make_pipeline(
                ColumnTransformer([("numeric", make_pipeline(SimpleImputer(), StandardScaler()), columns)]),
                LogisticRegression(C=1.0, max_iter=1000),
            )
            model.fit(train[columns], train.home_win.astype(int))
            prob = model.predict_proba(test[columns])[:, 1]
            y = test.home_win.astype(int)
            folds.append({
                "season": int(test_season),
                "n": len(test),
                "accuracy": accuracy_score(y, prob >= 0.5),
                "log_loss": log_loss(y, prob, labels=[0, 1]),
                "brier": brier_score_loss(y, prob),
            })
        if folds:
            results["models"][name] = folds

    results["coverage"] = {
        column: float(frame[column].notna().mean())
        for column in sorted({c for cols in candidates.values() for c in cols})
    }
    output_path = output_path or input_path.with_suffix(".analysis.json")
    output_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return output_path
