"""Walk-forward fixed-offset residual fitting (M08)."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from pick_prophet.evaluation.artifacts import (
    sampling_frame_for_row,
    write_predictions,
    write_summary,
)
from pick_prophet.evaluation.folds import expanding_folds
from pick_prophet.evaluation.metrics import score_probabilities
from pick_prophet.evaluation.protocol import load_protocol
from pick_prophet.features.matrix_schema import MATRIX_SCHEMA_VERSION
from pick_prophet.models.fixed_offset_logit import (
    fit_fixed_offset_logit,
    predict_raw,
    sigmoid,
)
from pick_prophet.models.residual_bundle import BUNDLE_SCHEMA_VERSION, write_bundle
from pick_prophet.models.residual_preprocess import FoldPreprocessor
from pick_prophet.models.residual_variants import VARIANTS, assert_variants_valid

BASELINE_CONSISTENCY_TOL = 1e-6
SCORE_CLIP = 1e-15


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def load_matrix_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def validate_baseline_consistency(
    rows: list[dict[str, Any]], *, tol: float = BASELINE_CONSISTENCY_TOL
) -> None:
    for row in rows:
        logit = _as_float(row.get("home_market_logit"))
        prob = _as_float(row.get("home_implied_prob"))
        if logit is None or prob is None:
            continue
        expected = float(sigmoid(logit))
        if abs(expected - prob) > tol:
            raise ValueError(
                f"baseline inconsistency game_id={row.get('game_id')}: "
                f"sigma(logit)={expected} vs home_implied_prob={prob}"
            )


def eligibility(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in rows:
        game_id = row.get("game_id")
        y = _as_int(row.get("home_win"))
        logit = _as_float(row.get("home_market_logit"))
        if y not in (0, 1):
            excluded.append(
                {
                    "game_id": game_id,
                    "reason_code": "missing_or_invalid_target",
                }
            )
            continue
        if logit is None or not math.isfinite(logit):
            excluded.append(
                {
                    "game_id": game_id,
                    "reason_code": "missing_or_invalid_market_logit",
                }
            )
            continue
        kept.append(row)
    return kept, excluded


def _clip_score(p: float) -> float:
    return min(max(float(p), SCORE_CLIP), 1.0 - SCORE_CLIP)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fit_residual_walkforward(
    matrix_path: Path,
    output_dir: Path,
    *,
    protocol_version: str = "1.0.0",
    matrix_schema_version: str = MATRIX_SCHEMA_VERSION,
    variants: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    active_variants = variants if variants is not None else VARIANTS
    if variants is None:
        assert_variants_valid()
    if "market_only" not in active_variants:
        raise ValueError("variants must include market_only")
    if matrix_schema_version != MATRIX_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported matrix schema {matrix_schema_version!r}; "
            f"expected {MATRIX_SCHEMA_VERSION!r}"
        )
    protocol = load_protocol(protocol_version)
    rows = load_matrix_rows(matrix_path)
    validate_baseline_consistency(rows)

    seasons = sorted({int(r["season"]) for r in rows if r.get("season") not in (None, "")})
    folds = expanding_folds(seasons, protocol)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_predictions: list[dict[str, Any]] = []
    residual_details: list[dict[str, Any]] = []
    eligibility_rows: list[dict[str, Any]] = []
    fold_summaries: list[dict[str, Any]] = []
    bundle_hashes: dict[str, str] = {}

    import scipy

    for fold in folds:
        train_rows = [r for r in rows if int(r["season"]) in fold.train_seasons]
        test_rows = [r for r in rows if int(r["season"]) == fold.test_season]
        train_eligible, train_excl = eligibility(train_rows)
        test_eligible, test_excl = eligibility(test_rows)
        for side, excl in (("train", train_excl), ("test", test_excl)):
            for item in excl:
                eligibility_rows.append(
                    {
                        "fold_id": fold.fold_id,
                        "split": side,
                        **item,
                    }
                )
        eligibility_rows.append(
            {
                "fold_id": fold.fold_id,
                "split": "train",
                "game_id": "",
                "reason_code": "counts",
                "input_rows": len(train_rows),
                "eligible_rows": len(train_eligible),
                "excluded_rows": len(train_excl),
            }
        )
        eligibility_rows.append(
            {
                "fold_id": fold.fold_id,
                "split": "test",
                "game_id": "",
                "reason_code": "counts",
                "input_rows": len(test_rows),
                "eligible_rows": len(test_eligible),
                "excluded_rows": len(test_excl),
            }
        )

        canonical_ids = [int(r["game_id"]) for r in test_eligible]
        if len(canonical_ids) != len(set(canonical_ids)):
            raise ValueError(f"{fold.fold_id}: duplicate eligible test game_id")

        if not train_eligible or not test_eligible:
            eligibility_rows.append(
                {
                    "fold_id": fold.fold_id,
                    "split": "fold",
                    "game_id": "",
                    "reason_code": "skipped_empty_eligible",
                    "input_rows": len(train_rows) + len(test_rows),
                    "eligible_rows": len(train_eligible) + len(test_eligible),
                    "excluded_rows": "",
                }
            )
            continue

        fold_metrics: dict[str, Any] = {"fold_id": fold.fold_id, "variants": {}}

        for variant, columns in active_variants.items():
            if variant == "market_only":
                beta = np.zeros(0)
                feature_names: list[str] = []
                prep_state: dict[str, Any] = {"columns": [], "feature_names": []}
                x_test = np.zeros((len(test_eligible), 0))
                offsets = np.array(
                    [_as_float(r["home_market_logit"]) for r in test_eligible],
                    dtype=float,
                )
                p_raw = predict_raw(offsets, x_test, beta)
                adj = np.zeros(len(test_eligible))
                nit = 0
                fun = 0.0
                message = "market_only"
            else:
                prep = FoldPreprocessor(columns).fit(train_eligible)
                x_train = prep.transform(train_eligible)
                y_train = np.array(
                    [_as_int(r["home_win"]) for r in train_eligible], dtype=float
                )
                o_train = np.array(
                    [_as_float(r["home_market_logit"]) for r in train_eligible],
                    dtype=float,
                )
                fit = fit_fixed_offset_logit(x_train, y_train, o_train, lam=1.0)
                x_test = prep.transform(test_eligible)
                offsets = np.array(
                    [_as_float(r["home_market_logit"]) for r in test_eligible],
                    dtype=float,
                )
                p_raw = predict_raw(offsets, x_test, fit.beta)
                adj = x_test @ fit.beta if fit.beta.size else np.zeros(len(test_eligible))
                beta = fit.beta
                feature_names = list(prep.feature_names_)
                prep_state = prep.state_dict()
                nit = fit.nit
                fun = fit.fun
                message = fit.message

            emitted_ids = [int(r["game_id"]) for r in test_eligible]
            if emitted_ids != canonical_ids:
                raise ValueError(
                    f"{fold.fold_id}/{variant}: emitted IDs differ from canonical set"
                )

            y_true = [_as_int(r["home_win"]) for r in test_eligible]
            metrics = score_probabilities(y_true, list(map(float, p_raw)))
            fold_metrics["variants"][variant] = metrics

            for i, row in enumerate(test_eligible):
                all_predictions.append(
                    {
                        "protocol_version": protocol.protocol_version,
                        "model": variant,
                        "fold_id": fold.fold_id,
                        "test_season": fold.test_season,
                        "game_id": int(row["game_id"]),
                        "week": _as_int(row.get("week")),
                        "y_true": y_true[i],
                        "p_home": float(p_raw[i]),
                        "sampling_frame": sampling_frame_for_row(row),
                    }
                )
                residual_details.append(
                    {
                        "model": variant,
                        "fold_id": fold.fold_id,
                        "test_season": fold.test_season,
                        "game_id": int(row["game_id"]),
                        "matrix_schema_version": matrix_schema_version,
                        "p_home": float(p_raw[i]),
                        "p_home_scored": _clip_score(float(p_raw[i])),
                        "market_logit": float(offsets[i]),
                        "adjustment": float(adj[i]),
                    }
                )

            bundle = {
                "beta": [float(v) for v in beta],
                "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
                "feature_names": feature_names,
                "fold_id": fold.fold_id,
                "ftol": 1e-12,
                "fun": float(fun),
                "gtol": 1e-8,
                "lam": 1.0,
                "matrix_schema_version": matrix_schema_version,
                "max_iter": 1000,
                "message": message,
                "nit": int(nit),
                "preprocessor": prep_state,
                "protocol_version": protocol.protocol_version,
                "scipy_version": scipy.__version__,
                "solver": "L-BFGS-B",
                "source_columns": list(columns),
                "test_season": fold.test_season,
                "train_seasons": list(fold.train_seasons),
                "variant": variant,
            }
            bundle_path = output_dir / f"bundle_{fold.fold_id}_{variant}.json"
            bundle_hashes[bundle_path.name] = write_bundle(bundle_path, bundle)

        fold_summaries.append(fold_metrics)

    pred_path = output_dir / "predictions.csv"
    write_predictions(
        all_predictions, pred_path, protocol_version=protocol.protocol_version
    )
    details_path = output_dir / "residual_details.csv"
    _write_csv(
        details_path,
        residual_details,
        fieldnames=[
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
    elig_path = output_dir / "eligibility.csv"
    _write_csv(
        elig_path,
        eligibility_rows,
        fieldnames=[
            "fold_id",
            "split",
            "game_id",
            "reason_code",
            "input_rows",
            "eligible_rows",
            "excluded_rows",
        ],
    )

    summary = {
        "folds": fold_summaries,
        "matrix_schema_version": matrix_schema_version,
        "protocol_version": protocol.protocol_version,
        "variants": list(active_variants),
    }
    summary_path = output_dir / "summary.json"
    write_summary(summary, summary_path)

    manifest = {
        "bundle_hashes": bundle_hashes,
        "eligibility_sha256": _sha256_file(elig_path),
        "matrix_path": str(matrix_path),
        "matrix_schema_version": matrix_schema_version,
        "matrix_sha256": _sha256_file(matrix_path),
        "predictions_sha256": _sha256_file(pred_path),
        "protocol_version": protocol.protocol_version,
        "residual_details_sha256": _sha256_file(details_path),
        "summary_sha256": _sha256_file(summary_path),
        "variants": list(active_variants),
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return summary


def _write_csv(
    path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
