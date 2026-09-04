"""Metrics that are also useful without fitting a model."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence
from typing import Any


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


def calibration_bins(
    y_true: Sequence[int],
    probabilities: Sequence[float],
    *,
    n_bins: int = 10,
) -> list[dict[str, float]]:
    """Equal-width calibration bins on [0, 1]."""

    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    if len(y_true) != len(probabilities):
        raise ValueError("y_true and probabilities must have the same length")
    buckets: list[list[tuple[int, float]]] = [[] for _ in range(n_bins)]
    for y, p in zip(y_true, probabilities, strict=True):
        clipped = min(max(float(p), 0.0), 1.0)
        index = min(int(clipped * n_bins), n_bins - 1)
        buckets[index].append((int(y), clipped))
    rows: list[dict[str, float]] = []
    width = 1.0 / n_bins
    for index, bucket in enumerate(buckets):
        lo = index * width
        hi = (index + 1) * width
        if not bucket:
            rows.append(
                {
                    "bin": float(index),
                    "lo": lo,
                    "hi": hi,
                    "count": 0.0,
                    "mean_predicted": float("nan"),
                    "mean_outcome": float("nan"),
                }
            )
            continue
        mean_p = sum(p for _, p in bucket) / len(bucket)
        mean_y = sum(y for y, _ in bucket) / len(bucket)
        rows.append(
            {
                "bin": float(index),
                "lo": lo,
                "hi": hi,
                "count": float(len(bucket)),
                "mean_predicted": mean_p,
                "mean_outcome": mean_y,
            }
        )
    return rows


def _metric_value(y: Sequence[int], p: Sequence[float], metric: str) -> float:
    scores = score_probabilities(y, p)
    if metric not in scores:
        raise ValueError(f"unknown metric {metric!r}")
    return float(scores[metric])


def bootstrap_paired_delta(
    weeks: Sequence[Any],
    y_true: Sequence[int],
    p_left: Sequence[float],
    p_right: Sequence[float],
    *,
    metric: str = "log_loss",
    n_boot: int = 500,
    seed: int = 20260904,
) -> dict[str, float]:
    """Week-clustered bootstrap of metric(right) - metric(left).

    Lower log_loss/Brier for ``p_right`` yields a negative delta (improvement).
    """

    n = len(y_true)
    if not (n == len(p_left) == len(p_right) == len(weeks)):
        raise ValueError("weeks, y_true, p_left, and p_right must align")
    if n == 0:
        raise ValueError("at least one row is required")

    by_week: dict[Any, list[int]] = {}
    for index, week in enumerate(weeks):
        by_week.setdefault(week, []).append(index)
    week_keys = sorted(by_week, key=lambda w: (str(type(w)), str(w)))
    rng = random.Random(seed)

    def delta_for(indices: Sequence[int]) -> float:
        y = [y_true[i] for i in indices]
        left = [p_left[i] for i in indices]
        right = [p_right[i] for i in indices]
        return _metric_value(y, right, metric) - _metric_value(y, left, metric)

    observed = delta_for(range(n))
    samples: list[float] = []
    for _ in range(n_boot):
        drawn_weeks = [week_keys[rng.randrange(len(week_keys))] for _ in week_keys]
        indices: list[int] = []
        for week in drawn_weeks:
            indices.extend(by_week[week])
        samples.append(delta_for(indices))
    samples.sort()
    lo = samples[int(0.025 * (len(samples) - 1))]
    hi = samples[int(0.975 * (len(samples) - 1))]
    return {
        "metric": metric,
        "delta": observed,
        "mean_delta": sum(samples) / len(samples),
        "ci_low": lo,
        "ci_high": hi,
        "n_boot": n_boot,
        "seed": seed,
    }
