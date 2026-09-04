"""Metrics that are also useful without fitting a model."""

from __future__ import annotations

import math
from collections.abc import Iterable


def score_probabilities(
    y_true: Iterable[int], probabilities: Iterable[float]
) -> dict[str, float]:
    pairs = list(zip(y_true, probabilities, strict=True))
    if not pairs:
        raise ValueError("at least one prediction is required")
    clipped = [(y, min(max(float(p), 1e-15), 1 - 1e-15)) for y, p in pairs]
    return {
        "n": len(clipped),
        "accuracy": sum((p >= 0.5) == bool(y) for y, p in clipped) / len(clipped),
        "log_loss": -sum(
            y * math.log(p) + (1 - y) * math.log(1 - p) for y, p in clipped
        )
        / len(clipped),
        "brier": sum((p - y) ** 2 for y, p in clipped) / len(clipped),
    }
