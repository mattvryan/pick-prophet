"""Promotion policy load/validate for M12 evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pick_prophet.registry.hashing import sha256_file

POLICY_SCHEMA_VERSION = "1.0.0"

REQUIRED_POLICY_KEYS = {
    "artifact_schema_version",
    "policy_version",
    "log_loss_improvement_max_delta",
    "brier_improvement_max_delta",
    "uncertainty_method",
    "require_uncertainty_ci_excludes_zero",
    "calibration_metric",
    "max_calibration_regression",
    "min_paired_games",
    "min_test_seasons",
    "min_games_per_season",
    "min_seasons_improving_log_loss",
    "min_seasons_improving_brier",
    "min_prediction_coverage",
    "eligible_coverage_definition",
    "allowed_timing_classifications",
    "fail_closed_leakage_statuses",
}


def load_promotion_policy(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    digest = sha256_file(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(
            f"promotion policy hash mismatch for {path}: "
            f"expected {expected_sha256}, got {digest}"
        )
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise TypeError("promotion policy must be an object")
    missing = REQUIRED_POLICY_KEYS - set(payload)
    if missing:
        raise ValueError(f"promotion policy missing keys: {sorted(missing)}")
    if payload["artifact_schema_version"] != POLICY_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported promotion policy schema "
            f"{payload['artifact_schema_version']!r}"
        )
    payload = dict(payload)
    payload["_sha256"] = digest
    return payload


def default_promotion_policy() -> dict[str, Any]:
    """Immutable v1 thresholds (also written into the committed pack)."""
    return {
        "artifact_schema_version": POLICY_SCHEMA_VERSION,
        "policy_version": "1.0.0",
        "log_loss_improvement_max_delta": -1.0e-6,
        "brier_improvement_max_delta": -1.0e-6,
        "uncertainty_method": "week_cluster_bootstrap",
        "require_uncertainty_ci_excludes_zero": True,
        "calibration_metric": "ece",
        "max_calibration_regression": 0.01,
        "min_paired_games": 100,
        "min_test_seasons": 2,
        "min_games_per_season": 25,
        "min_seasons_improving_log_loss": 2,
        "min_seasons_improving_brier": 2,
        "min_prediction_coverage": 0.95,
        "eligible_coverage_definition": (
            "fraction of paired held-out rows with finite candidate and "
            "baseline probabilities"
        ),
        "allowed_timing_classifications": ["pre_lock"],
        "fail_closed_leakage_statuses": [
            "unresolved",
            "fail",
            "leakage_detected",
        ],
        "notes": (
            "Lower log-loss and Brier are better. Deltas are candidate − "
            "baseline; improvement requires delta <= max_delta (negative)."
        ),
    }
