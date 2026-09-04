"""M09 residual inference and calibration diagnostics (raw p_home only)."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from pick_prophet.evaluation.cluster_bootstrap import (
    bootstrap_paired_delta_clusters,
    cluster_keys,
)
from pick_prophet.evaluation.holm import holm_adjust
from pick_prophet.evaluation.metrics import calibration_bins, score_probabilities
from pick_prophet.evaluation.protocol import ProtocolConfig, load_protocol

PROB_AGREE_TOL = 1e-12
FLIP_EPS = 1e-12
CAL_EPS = 1e-6
CAL_MAX_ITER = 200
CAL_FTOL = 1e-12
ADJUSTMENT_BANDS: tuple[tuple[float, float | None], ...] = (
    (0.0, 0.05),
    (0.05, 0.15),
    (0.15, 0.30),
    (0.30, None),
)
REQUIRED_PRED_FILES = (
    "predictions.csv",
    "residual_details.csv",
    "eligibility.csv",
    "run_manifest.json",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _as_float(value: Any, *, field: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric {field}: {value!r}") from exc
    if not math.isfinite(out):
        raise ValueError(f"non-finite {field}: {value!r}")
    return out


def _as_int(value: Any, *, field: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-integer {field}: {value!r}") from exc


def _favorite_band(spread: Any) -> str:
    if spread is None or spread == "":
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


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _pred_key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(row["model"]),
        str(row["fold_id"]),
        _as_int(row["test_season"], field="test_season"),
        _as_int(row["game_id"], field="game_id"),
    )


def _classify_side(p: float) -> str:
    if p > 0.5 + FLIP_EPS:
        return "home"
    if p < 0.5 - FLIP_EPS:
        return "away"
    return "tie"


def _band_label(lo: float, hi: float | None) -> str:
    if hi is None:
        return f"[{lo:g},inf)"
    return f"[{lo:g},{hi:g})"


def _row_in_slice(row: dict[str, Any], name: str) -> bool:
    week = _as_int(row["week"], field="week")
    if name == "overall":
        return True
    if name == "week_1":
        return week == 1
    if name == "weeks_1_3":
        return 1 <= week <= 3
    if name == "weeks_4_plus":
        return week >= 4
    if name == "neutral_site":
        return _truthy(row.get("neutral_site"))
    if name == "favorite_lt_3":
        return row["_favorite_band"] == "lt_3"
    if name == "favorite_3_to_7":
        return row["_favorite_band"] == "3_to_7"
    if name == "favorite_gt_7":
        return row["_favorite_band"] == "gt_7"
    if name == "missing_spread":
        return row["_favorite_band"] == "missing_spread"
    if name == "all_fbs":
        return row.get("sampling_frame") == "all_fbs"
    if name == "verified_espn_pickem":
        return row.get("sampling_frame") == "verified_espn_pickem"
    raise ValueError(f"unknown slice {name!r}")


def fit_calibration_glm(
    y_true: Sequence[int],
    probabilities: Sequence[float],
    *,
    eps: float = CAL_EPS,
) -> dict[str, Any]:
    """Unpenalized Cox-style calibration: y ~ σ(a + b logit(p_ε))."""

    n = len(y_true)
    base = {
        "n": n,
        "eps": eps,
        "a": None,
        "b": None,
        "a_ideal": 0.0,
        "b_ideal": 1.0,
        "status": "not_estimable",
        "reason": "",
        "nit": 0,
    }
    if n < 2:
        base["reason"] = "insufficient_rows"
        return base
    if len({int(y) for y in y_true}) < 2:
        base["reason"] = "single_class"
        return base

    y = np.asarray([int(v) for v in y_true], dtype=float)
    p = np.asarray([float(v) for v in probabilities], dtype=float)
    p_clip = np.clip(p, eps, 1.0 - eps)
    logit_p = np.log(p_clip) - np.log1p(-p_clip)

    def nll(theta: np.ndarray) -> float:
        a, b = float(theta[0]), float(theta[1])
        eta = a + b * logit_p
        return float(np.mean(np.logaddexp(0.0, eta) - y * eta))

    def grad(theta: np.ndarray) -> np.ndarray:
        a, b = float(theta[0]), float(theta[1])
        eta = a + b * logit_p
        resid = 1.0 / (1.0 + np.exp(-eta)) - y
        return np.array(
            [float(np.mean(resid)), float(np.mean(resid * logit_p))],
            dtype=float,
        )

    result = minimize(
        nll,
        x0=np.array([0.0, 1.0], dtype=float),
        jac=grad,
        method="L-BFGS-B",
        options={"maxiter": CAL_MAX_ITER, "ftol": CAL_FTOL},
    )
    if not result.success:
        base["reason"] = "non_convergence"
        base["nit"] = int(result.nit)
        base["status"] = "failed"
        return base

    a, b = float(result.x[0]), float(result.x[1])
    if not (math.isfinite(a) and math.isfinite(b)):
        base["reason"] = "non_finite_params"
        base["status"] = "failed"
        base["nit"] = int(result.nit)
        return base

    # Curvature / separation heuristic: huge |b| or |a|
    if abs(a) > 50 or abs(b) > 50:
        base["reason"] = "separation"
        base["status"] = "not_estimable"
        base["nit"] = int(result.nit)
        return base

    return {
        "n": n,
        "eps": eps,
        "a": a,
        "b": b,
        "a_ideal": 0.0,
        "b_ideal": 1.0,
        "status": "ok",
        "reason": "",
        "nit": int(result.nit),
    }


def _validate_and_load(
    predictions_dir: Path,
    matrix_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    predictions_dir = predictions_dir.resolve()
    matrix_path = matrix_path.resolve()
    for name in REQUIRED_PRED_FILES:
        if not (predictions_dir / name).is_file():
            raise ValueError(f"missing required artifact {name}")

    manifest = json.loads((predictions_dir / "run_manifest.json").read_text())
    checks = {
        "predictions_sha256": predictions_dir / "predictions.csv",
        "residual_details_sha256": predictions_dir / "residual_details.csv",
        "eligibility_sha256": predictions_dir / "eligibility.csv",
    }
    for key, path in checks.items():
        expected = manifest.get(key)
        actual = _sha256_file(path)
        if expected != actual:
            raise ValueError(f"hash mismatch for {path.name}: manifest {expected} != {actual}")
    matrix_expected = manifest.get("matrix_sha256")
    matrix_actual = _sha256_file(matrix_path)
    if matrix_expected != matrix_actual:
        raise ValueError(
            f"matrix hash mismatch: manifest {matrix_expected} != {matrix_actual}"
        )

    preds = _read_csv(predictions_dir / "predictions.csv")
    details = _read_csv(predictions_dir / "residual_details.csv")
    eligibility = _read_csv(predictions_dir / "eligibility.csv")
    matrix_rows = _read_csv(matrix_path)

    if not preds:
        raise ValueError("predictions.csv is empty")

    detail_by_key: dict[tuple[str, str, int, int], dict[str, str]] = {}
    for row in details:
        key = _pred_key(row)
        if key in detail_by_key:
            raise ValueError(f"duplicate residual_details key {key}")
        detail_by_key[key] = row

    matrix_by_id: dict[int, dict[str, str]] = {}
    for row in matrix_rows:
        gid = _as_int(row["game_id"], field="game_id")
        if gid in matrix_by_id:
            raise ValueError(f"duplicate matrix game_id {gid}")
        matrix_by_id[gid] = row

    seen_pred: set[tuple[str, str, int, int]] = set()
    enriched: list[dict[str, Any]] = []
    for row in preds:
        key = _pred_key(row)
        if key in seen_pred:
            raise ValueError(f"duplicate prediction key {key}")
        seen_pred.add(key)
        if key not in detail_by_key:
            raise ValueError(f"prediction missing residual detail for {key}")
        detail = detail_by_key[key]
        p_pred = _as_float(row["p_home"], field="p_home")
        p_detail = _as_float(detail["p_home"], field="detail.p_home")
        if p_pred < 0.0 or p_pred > 1.0:
            raise ValueError(f"p_home out of [0,1] for {key}: {p_pred}")
        if abs(p_pred - p_detail) > PROB_AGREE_TOL:
            raise ValueError(
                f"p_home mismatch pred vs detail for {key}: {p_pred} vs {p_detail}"
            )
        gid = key[3]
        if gid not in matrix_by_id:
            raise ValueError(f"game_id {gid} missing from matrix")
        mrow = matrix_by_id[gid]
        season = _as_int(mrow["season"], field="season")
        test_season = key[2]
        if season != test_season:
            raise ValueError(
                f"matrix season {season} != prediction test_season {test_season} for {gid}"
            )
        for col in ("season_type", "neutral_site", "spread_home", "week"):
            if col not in mrow:
                raise ValueError(f"matrix missing required column {col}")
        item = {
            "protocol_version": row.get("protocol_version"),
            "model": key[0],
            "fold_id": key[1],
            "test_season": test_season,
            "game_id": gid,
            "week": _as_int(mrow["week"], field="week"),
            "season_type": str(mrow["season_type"]),
            "y_true": _as_int(row["y_true"], field="y_true"),
            "p_home": p_pred,
            "sampling_frame": row.get("sampling_frame") or "all_fbs",
            "neutral_site": mrow["neutral_site"],
            "spread_home": mrow.get("spread_home"),
            "adjustment": _as_float(detail.get("adjustment", 0.0), field="adjustment"),
            "market_logit": _as_float(detail.get("market_logit", 0.0), field="market_logit"),
        }
        item["_favorite_band"] = _favorite_band(item["spread_home"])
        enriched.append(item)

    return enriched, eligibility, manifest


def _pair_variant(
    rows: Sequence[dict[str, Any]], variant: str
) -> list[dict[str, Any]]:
    by_fold_game: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        key = (str(row["fold_id"]), int(row["game_id"]))
        by_fold_game[key][str(row["model"])] = row

    paired: list[dict[str, Any]] = []
    for (fold_id, game_id), models in sorted(by_fold_game.items()):
        if "market_only" not in models:
            raise ValueError(
                f"missing market_only for fold={fold_id} game_id={game_id}"
            )
        if variant not in models:
            continue
        market = models["market_only"]
        cand = models[variant]
        if int(market["y_true"]) != int(cand["y_true"]):
            raise ValueError(f"y_true mismatch for {fold_id}/{game_id}")
        paired.append(
            {
                **cand,
                "p_market": float(market["p_home"]),
                "p_candidate": float(cand["p_home"]),
            }
        )

    cand_ids = {
        (str(r["fold_id"]), int(r["game_id"]))
        for r in rows
        if str(r["model"]) == variant
    }
    market_ids = {
        (str(r["fold_id"]), int(r["game_id"]))
        for r in rows
        if str(r["model"]) == "market_only"
    }
    if cand_ids != market_ids:
        missing = sorted(cand_ids - market_ids)
        extra = sorted(market_ids - cand_ids)
        raise ValueError(
            f"unequal paired game IDs for {variant}: "
            f"cand_only={missing[:5]} market_only_extra={extra[:5]}"
        )
    if not paired:
        raise ValueError(f"empty paired set for {variant}")
    return paired


def _subset(rows: Sequence[dict[str, Any]], slice_name: str) -> list[dict[str, Any]]:
    return [row for row in rows if _row_in_slice(row, slice_name)]


def _game_id_fingerprint(rows: Sequence[dict[str, Any]]) -> tuple[int, ...]:
    return tuple(sorted(int(r["game_id"]) for r in rows))


def _metrics_block(rows: Sequence[dict[str, Any]], *, p_key: str) -> dict[str, float]:
    y = [int(r["y_true"]) for r in rows]
    p = [float(r[p_key]) for r in rows]
    return score_probabilities(y, p)


def _flip_counts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    flip = agree = cand_tie = market_tie = 0
    for row in rows:
        c = _classify_side(float(row["p_candidate"]))
        m = _classify_side(float(row["p_market"]))
        if c == "tie":
            cand_tie += 1
            continue
        if m == "tie":
            market_tie += 1
            continue
        if c == m:
            agree += 1
        else:
            flip += 1
    n = len(rows)
    return {
        "n": n,
        "flip": flip,
        "agree": agree,
        "candidate_tie": cand_tie,
        "market_tie": market_tie,
        "flip_rate": flip / n if n else 0.0,
        "agree_rate": agree / n if n else 0.0,
    }


def diagnose_residual(
    predictions_dir: Path,
    matrix_path: Path,
    out_dir: Path,
    *,
    protocol_version: str = "1.0.0",
    protocol: ProtocolConfig | None = None,
    n_boot: int | None = None,
) -> dict[str, Path]:
    """Compute M09 diagnostics on raw M08 predictions; never rewrite p_home."""

    protocol = protocol or load_protocol(protocol_version)
    boot_n = protocol.n_boot if n_boot is None else int(n_boot)
    seed = protocol.bootstrap_seed
    rows, eligibility, manifest = _validate_and_load(predictions_dir, matrix_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    variants = sorted({str(r["model"]) for r in rows})
    if "market_only" not in variants:
        raise ValueError("predictions missing market_only")
    candidates = [v for v in variants if v != "market_only"]

    slice_names = ("overall",) + tuple(protocol.required_slices)

    overall_metric_rows: list[dict[str, Any]] = []
    paired_boot_rows: list[dict[str, Any]] = []
    slice_metric_rows: list[dict[str, Any]] = []
    reliability_rows: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    adjustment_rows: list[dict[str, Any]] = []
    flip_rows: list[dict[str, Any]] = []
    fold_consistency_rows: list[dict[str, Any]] = []

    # Holm inventory: list of dicts with p or None + metadata
    holm_items: list[dict[str, Any]] = []
    seen_hypotheses: dict[tuple[str, tuple[int, ...]], int] = {}

    for variant in candidates:
        paired = _pair_variant(rows, variant)
        folds = sorted({str(r["fold_id"]) for r in paired})

        # Aggregate + fold overall metrics
        for scope, subset in [("aggregate", paired)] + [
            (fold, [r for r in paired if str(r["fold_id"]) == fold]) for fold in folds
        ]:
            if not subset:
                continue
            m_c = _metrics_block(subset, p_key="p_candidate")
            m_m = _metrics_block(subset, p_key="p_market")
            overall_metric_rows.append(
                {
                    "variant": variant,
                    "scope": scope,
                    "n": m_c["n"],
                    "accuracy": m_c["accuracy"],
                    "log_loss": m_c["log_loss"],
                    "brier": m_c["brier"],
                    "delta_accuracy": m_c["accuracy"] - m_m["accuracy"],
                    "delta_log_loss": m_c["log_loss"] - m_m["log_loss"],
                    "delta_brier": m_c["brier"] - m_m["brier"],
                }
            )
            if scope != "aggregate":
                fold_consistency_rows.append(
                    {
                        "variant": variant,
                        "fold_id": scope,
                        "n": m_c["n"],
                        "delta_accuracy": m_c["accuracy"] - m_m["accuracy"],
                        "delta_log_loss": m_c["log_loss"] - m_m["log_loss"],
                        "delta_brier": m_c["brier"] - m_m["brier"],
                        "delta_log_loss_sign": (
                            0
                            if abs(m_c["log_loss"] - m_m["log_loss"]) < 1e-15
                            else (1 if m_c["log_loss"] - m_m["log_loss"] > 0 else -1)
                        ),
                    }
                )

            # Reliability
            bins = calibration_bins(
                [int(r["y_true"]) for r in subset],
                [float(r["p_candidate"]) for r in subset],
                n_bins=protocol.calibration_bins,
            )
            for bin_row in bins:
                reliability_rows.append(
                    {
                        "variant": variant,
                        "scope": scope,
                        "boundary_convention": "equal_width_rightmost_closed",
                        **bin_row,
                    }
                )

            # Calibration
            cal = fit_calibration_glm(
                [int(r["y_true"]) for r in subset],
                [float(r["p_candidate"]) for r in subset],
            )
            calibration_rows.append(
                {
                    "variant": variant,
                    "scope": scope,
                    **cal,
                }
            )

        # Flips + adjustment bands on aggregate
        flips = _flip_counts(paired)
        flip_rows.append({"variant": variant, "scope": "aggregate", **flips})
        for lo, hi in ADJUSTMENT_BANDS:
            band_rows = [
                r
                for r in paired
                if abs(float(r["adjustment"])) >= lo
                and (hi is None or abs(float(r["adjustment"])) < hi)
            ]
            n_band = len(band_rows)
            flip_band = _flip_counts(band_rows) if band_rows else {
                "flip": 0,
                "flip_rate": 0.0,
            }
            mean_abs = (
                sum(abs(float(r["adjustment"])) for r in band_rows) / n_band
                if n_band
                else float("nan")
            )
            mean_signed = (
                sum(float(r["adjustment"]) for r in band_rows) / n_band
                if n_band
                else float("nan")
            )
            mean_dp = (
                sum(float(r["p_candidate"]) - float(r["p_market"]) for r in band_rows)
                / n_band
                if n_band
                else float("nan")
            )
            adjustment_rows.append(
                {
                    "variant": variant,
                    "band": _band_label(lo, hi),
                    "n": n_band,
                    "n_total": len(paired),
                    "coverage": n_band / len(paired) if paired else 0.0,
                    "mean_abs_adjustment": mean_abs,
                    "mean_signed_adjustment": mean_signed,
                    "mean_prob_change": mean_dp,
                    "flip": flip_band["flip"],
                    "flip_rate": flip_band["flip_rate"],
                }
            )

        # Confirmatory slices
        for slice_name in slice_names:
            subset = _subset(paired, slice_name)
            contrast_base = f"{variant}|{slice_name}"
            inventory = {
                "variant": variant,
                "slice": slice_name,
                "analysis": "confirmatory",
                "n": len(subset),
                "predeclared": True,
            }
            if not subset:
                contrast_id = f"{contrast_base}|log_loss"
                slice_metric_rows.append(
                    {
                        **inventory,
                        "status": "empty",
                        "reason": "empty_slice",
                        "accuracy": "",
                        "log_loss": "",
                        "brier": "",
                        "delta_log_loss": "",
                        "raw_p": "",
                        "holm_p": "",
                        "holm_reject_0.05": "",
                        "holm_rank": "",
                        "holm_family_size": "",
                        "hypothesis_id": contrast_id,
                        "deduped_of": "",
                    }
                )
                holm_items.append(
                    {
                        **inventory,
                        "p_value": None,
                        "reason": "empty_slice",
                        "fingerprint": None,
                        "contrast_id": contrast_id,
                    }
                )
                continue

            m_c = _metrics_block(subset, p_key="p_candidate")
            m_m = _metrics_block(subset, p_key="p_market")
            clusters = cluster_keys(
                [r["test_season"] for r in subset],
                [r["season_type"] for r in subset],
                [r["week"] for r in subset],
            )
            y = [int(r["y_true"]) for r in subset]
            p_left = [float(r["p_market"]) for r in subset]
            p_right = [float(r["p_candidate"]) for r in subset]
            boot_by_metric: dict[str, dict[str, Any]] = {}
            for metric in ("log_loss", "brier", "accuracy"):
                contrast_id = f"{contrast_base}|{metric}"
                boot = bootstrap_paired_delta_clusters(
                    clusters,
                    y,
                    p_left,
                    p_right,
                    metric=metric,
                    n_boot=boot_n,
                    seed=seed,
                    contrast_id=contrast_id,
                )
                boot_by_metric[metric] = boot
                paired_boot_rows.append(
                    {
                        "variant": variant,
                        "slice": slice_name,
                        "analysis": "confirmatory",
                        **boot,
                    }
                )

            fp = _game_id_fingerprint(subset)
            hyp_key = (variant, fp)
            contrast_id = f"{contrast_base}|log_loss"
            deduped_of = ""
            p_for_holm: float | None = float(boot_by_metric["log_loss"]["p_value"])
            reason = ""
            if hyp_key in seen_hypotheses:
                # Identical population already represented — keep label, skip Holm
                primary_idx = seen_hypotheses[hyp_key]
                deduped_of = holm_items[primary_idx]["contrast_id"]
                p_for_holm = None
                reason = "duplicate_population"
            else:
                seen_hypotheses[hyp_key] = len(holm_items)

            holm_items.append(
                {
                    **inventory,
                    "p_value": p_for_holm,
                    "reason": reason,
                    "fingerprint": fp,
                    "contrast_id": contrast_id,
                    "metrics": m_c,
                    "delta_log_loss": m_c["log_loss"] - m_m["log_loss"],
                    "delta_brier": m_c["brier"] - m_m["brier"],
                    "delta_accuracy": m_c["accuracy"] - m_m["accuracy"],
                    "deduped_of": deduped_of,
                }
            )
            slice_metric_rows.append(
                {
                    **inventory,
                    "status": "ok",
                    "reason": reason,
                    "accuracy": m_c["accuracy"],
                    "log_loss": m_c["log_loss"],
                    "brier": m_c["brier"],
                    "delta_accuracy": m_c["accuracy"] - m_m["accuracy"],
                    "delta_log_loss": m_c["log_loss"] - m_m["log_loss"],
                    "delta_brier": m_c["brier"] - m_m["brier"],
                    "raw_p": p_for_holm if p_for_holm is not None else "",
                    "holm_p": "",
                    "holm_reject_0.05": "",
                    "holm_rank": "",
                    "holm_family_size": "",
                    "hypothesis_id": contrast_id,
                    "deduped_of": deduped_of,
                    "n_clusters": boot_by_metric["log_loss"]["n_clusters"],
                }
            )

    # Also emit market_only absolute metrics (no deltas)
    market_rows = [r for r in rows if str(r["model"]) == "market_only"]
    if market_rows:
        # Deduplicate by fold/game (one row per game in market_only)
        uniq = {(r["fold_id"], r["game_id"]): r for r in market_rows}
        market_list = list(uniq.values())
        m = _metrics_block(
            [{**r, "p_candidate": r["p_home"]} for r in market_list],
            p_key="p_candidate",
        )
        overall_metric_rows.insert(
            0,
            {
                "variant": "market_only",
                "scope": "aggregate",
                "n": m["n"],
                "accuracy": m["accuracy"],
                "log_loss": m["log_loss"],
                "brier": m["brier"],
                "delta_accuracy": "",
                "delta_log_loss": "",
                "delta_brier": "",
            },
        )

    predeclared_family = len(candidates) * len(slice_names)
    p_list = [item["p_value"] for item in holm_items]
    holm_rows = holm_adjust(p_list, alpha=0.05)
    realized = holm_rows[0]["family_size"] if holm_rows else 0
    holm_by_contrast = {
        item["contrast_id"]: (item, adj)
        for item, adj in zip(holm_items, holm_rows, strict=True)
    }

    for row in slice_metric_rows:
        hid = row.get("hypothesis_id") or f"{row['variant']}|{row['slice']}|log_loss"
        if hid not in holm_by_contrast:
            continue
        item, adj = holm_by_contrast[hid]
        row["holm_family_size"] = adj["family_size"]
        row["hypothesis_id"] = hid
        if adj["raw_p"] is None:
            row["raw_p"] = ""
            row["holm_p"] = ""
            row["holm_reject_0.05"] = ""
            row["holm_rank"] = ""
            if not row.get("reason"):
                row["reason"] = item.get("reason") or "non_estimable"
        else:
            row["raw_p"] = adj["raw_p"]
            row["holm_p"] = adj["holm_p"]
            row["holm_reject_0.05"] = bool(adj["reject"])
            row["holm_rank"] = adj["rank"]

    # Exclusions from M08 eligibility
    exclusion_rows: list[dict[str, Any]] = []
    for row in eligibility:
        exclusion_rows.append(
            {
                "fold_id": row.get("fold_id"),
                "split": row.get("split"),
                "game_id": row.get("game_id"),
                "reason_code": row.get("reason_code"),
                "input_rows": row.get("input_rows"),
                "eligible_rows": row.get("eligible_rows"),
                "excluded_rows": row.get("excluded_rows"),
                "source": "m08_eligibility",
            }
        )

    paths: dict[str, Path] = {}
    paths["overall_metrics"] = out_dir / "overall_metrics.csv"
    _write_csv(
        paths["overall_metrics"],
        overall_metric_rows,
        [
            "variant",
            "scope",
            "n",
            "accuracy",
            "log_loss",
            "brier",
            "delta_accuracy",
            "delta_log_loss",
            "delta_brier",
        ],
    )
    paths["paired_bootstrap"] = out_dir / "paired_bootstrap.csv"
    _write_csv(
        paths["paired_bootstrap"],
        paired_boot_rows,
        [
            "variant",
            "slice",
            "analysis",
            "metric",
            "contrast_id",
            "delta",
            "mean_delta",
            "ci_low",
            "ci_high",
            "p_value",
            "n_boot",
            "seed",
            "n_clusters",
            "n_rows",
        ],
    )
    paths["slice_metrics"] = out_dir / "slice_metrics.csv"
    _write_csv(
        paths["slice_metrics"],
        slice_metric_rows,
        [
            "variant",
            "slice",
            "analysis",
            "n",
            "predeclared",
            "status",
            "reason",
            "accuracy",
            "log_loss",
            "brier",
            "delta_accuracy",
            "delta_log_loss",
            "delta_brier",
            "raw_p",
            "holm_p",
            "holm_reject_0.05",
            "holm_rank",
            "holm_family_size",
            "hypothesis_id",
            "deduped_of",
            "n_clusters",
        ],
    )
    paths["reliability_bins"] = out_dir / "reliability_bins.csv"
    _write_csv(
        paths["reliability_bins"],
        reliability_rows,
        [
            "variant",
            "scope",
            "boundary_convention",
            "bin",
            "lo",
            "hi",
            "count",
            "mean_predicted",
            "mean_outcome",
        ],
    )
    paths["calibration_fit"] = out_dir / "calibration_fit.csv"
    _write_csv(
        paths["calibration_fit"],
        calibration_rows,
        [
            "variant",
            "scope",
            "n",
            "eps",
            "a",
            "b",
            "a_ideal",
            "b_ideal",
            "status",
            "reason",
            "nit",
        ],
    )
    paths["adjustment_bands"] = out_dir / "adjustment_bands.csv"
    _write_csv(
        paths["adjustment_bands"],
        adjustment_rows,
        [
            "variant",
            "band",
            "n",
            "n_total",
            "coverage",
            "mean_abs_adjustment",
            "mean_signed_adjustment",
            "mean_prob_change",
            "flip",
            "flip_rate",
        ],
    )
    paths["flip_summary"] = out_dir / "flip_summary.csv"
    _write_csv(
        paths["flip_summary"],
        flip_rows,
        [
            "variant",
            "scope",
            "n",
            "flip",
            "agree",
            "candidate_tie",
            "market_tie",
            "flip_rate",
            "agree_rate",
        ],
    )
    paths["fold_consistency"] = out_dir / "fold_consistency.csv"
    _write_csv(
        paths["fold_consistency"],
        fold_consistency_rows,
        [
            "variant",
            "fold_id",
            "n",
            "delta_accuracy",
            "delta_log_loss",
            "delta_brier",
            "delta_log_loss_sign",
        ],
    )
    paths["exclusions"] = out_dir / "exclusions.csv"
    _write_csv(
        paths["exclusions"],
        exclusion_rows,
        [
            "fold_id",
            "split",
            "game_id",
            "reason_code",
            "input_rows",
            "eligible_rows",
            "excluded_rows",
            "source",
        ],
    )

    summary = {
        "protocol_version": protocol.protocol_version,
        "n_boot": boot_n,
        "bootstrap_seed": seed,
        "ci_method": "percentile_linear_2.5_97.5",
        "p_value_method": "centered_cluster_bootstrap",
        "cluster_key": ["test_season", "season_type", "week"],
        "predictions_dir": str(Path(predictions_dir).resolve()),
        "matrix_path": str(Path(matrix_path).resolve()),
        "matrix_sha256": manifest.get("matrix_sha256"),
        "variants": variants,
        "candidates": candidates,
        "confirmatory_slices": list(slice_names),
        "holm": {
            "alpha": 0.05,
            "metric": "log_loss",
            "predeclared_family_size": predeclared_family,
            "realized_family_size": realized,
        },
        "raw_predictions_unchanged": True,
        "calibrated_candidate": False,
        "flip_eps": FLIP_EPS,
        "calibration_eps": CAL_EPS,
        "adjustment_bands": [_band_label(lo, hi) for lo, hi in ADJUSTMENT_BANDS],
    }
    paths["summary"] = out_dir / "summary.json"
    paths["summary"].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    report_lines = [
        "# Residual diagnostics (M09)",
        "",
        "Diagnostics are computed on **raw** M08 `p_home` only.",
        "No calibrated prediction candidate is produced; predictions are not rewritten.",
        "",
        f"- Protocol: `{protocol.protocol_version}`",
        f"- Bootstrap: n_boot={boot_n}, seed={seed}, cluster=`(test_season, season_type, week)`",
        f"- Holm confirmatory log-loss family: predeclared={predeclared_family}, realized={realized}",
        f"- Candidates: {', '.join(candidates)}",
        "",
        "## Overall deltas vs market_only (aggregate)",
        "",
    ]
    for row in overall_metric_rows:
        if row["variant"] == "market_only" or row["scope"] != "aggregate":
            continue
        report_lines.append(
            f"- `{row['variant']}`: n={row['n']}, "
            f"Δlog_loss={row['delta_log_loss']}, Δbrier={row['delta_brier']}, "
            f"Δacc={row['delta_accuracy']}"
        )
    report_lines.extend(
        [
            "",
            (
                "See CSV artifacts in this directory for bootstrap CIs, slices, "
                "reliability, calibration intercept/slope, flips, and adjustment bands."
            ),
            "",
        ]
    )
    paths["report"] = out_dir / "report.md"
    paths["report"].write_text("\n".join(report_lines))
    return paths
