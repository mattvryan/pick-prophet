"""M11 decision recording: no-challenger when M10 promotes nothing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pick_prophet.models.approved_feature_set import (
    EmptyPromotedFeaturesError,
    load_approved_feature_set,
    require_promoted_features_for_m11,
)

DEFAULT_M10_APPROVED_PATH = (
    "docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json"
)
DEFAULT_REOPENING_CONDITION = (
    "Reopen M11 only after a new M10 evidence version promotes at least one "
    "feature into promoted_features; review_only and rejected features remain "
    "ineligible."
)


class M10ArtifactHashMismatchError(ValueError):
    """Raised when the on-disk M10 approved artifact hash does not match."""


class IneligibleM11FeaturesError(ValueError):
    """Raised when review_only or rejected features are proposed for M11."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_m11_decision(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise TypeError(f"M11 decision must be an object: {path}")
    return payload


def validate_m10_approved_artifact(
    path: str | Path,
    *,
    expected_sha256: str,
    approved: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and hash-check the M10 approved feature set before any M11 decision."""
    path = Path(path)
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise M10ArtifactHashMismatchError(
            f"M10 approved feature set hash mismatch for {path}: "
            f"expected {expected_sha256}, got {actual}"
        )
    payload = (
        dict(approved) if approved is not None else load_approved_feature_set(path)
    )
    if "promoted_features" not in payload:
        raise ValueError(f"approved feature set missing promoted_features: {path}")
    return payload


def build_m11_feature_set(
    approved: Mapping[str, Any],
    *,
    candidate_features: Sequence[str],
) -> list[str]:
    """Allow only explicitly promoted features into an M11 feature set.

    ``review_only`` and ``rejected`` features are never eligible, even if a
    caller attempts to reinterpret them as approved.
    """
    candidates = [str(item) for item in candidate_features]
    review_only = {str(item) for item in approved.get("review_only_features") or []}
    rejected = {str(item) for item in approved.get("rejected_features") or []}
    promoted = {str(item) for item in approved.get("promoted_features") or []}

    bad_review = sorted({f for f in candidates if f in review_only})
    if bad_review:
        raise IneligibleM11FeaturesError(
            f"review_only features are not eligible for M11: {bad_review}"
        )
    bad_rejected = sorted({f for f in candidates if f in rejected})
    if bad_rejected:
        raise IneligibleM11FeaturesError(
            f"rejected features are not eligible for M11: {bad_rejected}"
        )
    not_promoted = sorted({f for f in candidates if f not in promoted})
    if not_promoted:
        raise IneligibleM11FeaturesError(
            f"features are not in promoted_features and cannot enter M11: "
            f"{not_promoted}"
        )
    return list(candidates)


def resolve_m11_feature_set_for_run(
    approved: Mapping[str, Any],
    *,
    allow_baseline_only: bool = False,
) -> list[str]:
    """Fail closed for a future M11 run until at least one feature is promoted."""
    return require_promoted_features_for_m11(
        approved,
        allow_baseline_only=allow_baseline_only,
    )


def record_no_challenger_decision(
    *,
    m10_approved_path: str | Path,
    expected_sha256: str,
    out_path: str | Path,
    reviewer: str,
    reviewed_at_utc: str,
    protocol_version: str = "1.0.0",
    matrix_schema_version: str = "1.0.0",
    m10_decision_version: str = "m10-decisions-1.0.0",
    m11_decision_version: str = "m11-decision-1.0.0",
    reopening_condition: str = DEFAULT_REOPENING_CONDITION,
) -> dict[str, Any]:
    """Validate the M10 artifact hash, then write the M11 not-run decision."""
    m10_path = Path(m10_approved_path)
    approved = validate_m10_approved_artifact(
        m10_path,
        expected_sha256=expected_sha256,
    )
    promoted = [str(item) for item in approved.get("promoted_features") or []]
    if promoted:
        raise ValueError(
            "record_no_challenger_decision requires empty promoted_features; "
            f"got {promoted}"
        )
    # Opt into baseline-only acknowledgment; still no challenger training.
    require_promoted_features_for_m11(approved, allow_baseline_only=True)

    posix = m10_path.as_posix()
    relative = (
        DEFAULT_M10_APPROVED_PATH
        if posix.endswith(DEFAULT_M10_APPROVED_PATH)
        else posix
    )
    payload: dict[str, Any] = {
        "status": "not_run_no_promoted_features",
        "challenger_trained": False,
        "baseline_retained": "market_only",
        "m10_approved_feature_set_path": relative,
        "m10_approved_feature_set_sha256": expected_sha256,
        "promoted_features": [],
        "review_only_features": list(approved.get("review_only_features") or []),
        "review_only_families": list(approved.get("review_only_families") or []),
        "protocol_version": protocol_version,
        "matrix_schema_version": matrix_schema_version,
        "m10_decision_version": m10_decision_version,
        "m11_decision_version": m11_decision_version,
        "decision_version": m11_decision_version,
        "reviewed_at_utc": reviewed_at_utc,
        "reviewer": reviewer,
        "reopening_condition": reopening_condition,
        "inference_seasons": list(approved.get("inference_seasons") or []),
        "outcome": (
            "Skipping M11 is an evidence-driven successful outcome; market_only "
            "baseline retained. No boosted challenger trained."
        ),
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


# Re-export for callers that only import this module.
__all__ = [
    "DEFAULT_M10_APPROVED_PATH",
    "DEFAULT_REOPENING_CONDITION",
    "EmptyPromotedFeaturesError",
    "IneligibleM11FeaturesError",
    "M10ArtifactHashMismatchError",
    "build_m11_feature_set",
    "load_m11_decision",
    "record_no_challenger_decision",
    "resolve_m11_feature_set_for_run",
    "sha256_file",
    "validate_m10_approved_artifact",
]
