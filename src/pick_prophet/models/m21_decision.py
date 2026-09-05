"""M21 fail-closed no-challenger decision recording."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class M20DecisionHashMismatchError(ValueError):
    """Raised when the reviewed M20 artifact does not match its expected hash."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_m21_no_challenger(
    *,
    approved_path: str | Path,
    expected_sha256: str,
    output_path: str | Path,
    reviewer: str,
    reviewed_at_utc: str,
) -> dict[str, Any]:
    """Hash-check M20, require an empty promote set, and record no training."""

    approved_path = Path(approved_path)
    actual = sha256_file(approved_path)
    if actual != expected_sha256:
        raise M20DecisionHashMismatchError(
            f"M20 approved feature-set hash mismatch: expected {expected_sha256}, "
            f"got {actual}"
        )
    approved = json.loads(approved_path.read_text())
    if approved.get("status") != "no_features_promoted":
        raise ValueError("M21 no-challenger requires status=no_features_promoted")
    if approved.get("promoted_features") != []:
        raise ValueError("M21 no-challenger requires an empty promoted feature set")

    payload = {
        "baseline_retained": "market_only",
        "challenger_trained": False,
        "contains_2026_outcomes": False,
        "decision_version": "m21-decision-2.0.0",
        "matrix_schema_version": "2.0.0",
        "m20_approved_feature_set_path": (
            "docs/modeling_artifacts/m20/2.0.0/approved_feature_set.json"
        ),
        "m20_approved_feature_set_sha256": expected_sha256,
        "model_bundle_created": False,
        "promoted_features": [],
        "protocol_version": "2.0.0",
        "registry_changed": False,
        "reopening_condition": (
            "A new frozen protocol and evidence cycle must human-promote at least "
            "one feature before another challenger attempt."
        ),
        "reviewed_at_utc": reviewed_at_utc,
        "reviewer": reviewer,
        "status": "complete_no_challenger",
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload
