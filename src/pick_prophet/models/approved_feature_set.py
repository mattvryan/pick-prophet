"""Approved feature-set gate for M11 (no training here)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class EmptyPromotedFeaturesError(ValueError):
    """Raised when M11 would start with an empty promoted feature set."""


def load_approved_feature_set(path: str | Path) -> dict[str, Any]:
    """Load a versioned M10 approved-feature-set JSON artifact."""
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"approved feature set must be an object: {path}")
    if "promoted_features" not in payload:
        raise ValueError(f"approved feature set missing promoted_features: {path}")
    return payload


def require_promoted_features_for_m11(
    approved: Mapping[str, Any],
    *,
    allow_baseline_only: bool = False,
) -> list[str]:
    """Return promoted features, or fail closed when the set is empty.

    M11 must not train a boosted challenger on an empty promote set unless the
    caller explicitly opts into a baseline-only / no-challenger outcome via
    ``allow_baseline_only=True``.
    """
    raw = approved.get("promoted_features")
    if raw is None:
        raise EmptyPromotedFeaturesError(
            "approved feature set missing promoted_features; M11 must fail closed"
        )
    features = [str(item) for item in raw]
    if not features and not allow_baseline_only:
        raise EmptyPromotedFeaturesError(
            "promoted_features is empty; M11 must fail closed unless design "
            "explicitly permits a baseline-only/no-challenger outcome "
            "(allow_baseline_only=True)"
        )
    return features
