"""Cluster-key paired bootstrap for M09 residual diagnostics."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import Any

from .metrics import score_probabilities


def contrast_rng(seed: int, contrast_id: str) -> random.Random:
    """Deterministic RNG stream keyed by protocol seed + stable contrast ID."""

    digest = hashlib.sha256(f"{seed}:{contrast_id}".encode()).hexdigest()
    derived = int(digest[:16], 16)
    return random.Random(derived)


def cluster_keys(
    test_seasons: Sequence[Any],
    season_types: Sequence[Any],
    weeks: Sequence[Any],
) -> list[tuple[Any, Any, Any]]:
    if not (len(test_seasons) == len(season_types) == len(weeks)):
        raise ValueError("test_seasons, season_types, and weeks must align")
    return [
        (season, season_type, week)
        for season, season_type, week in zip(
            test_seasons, season_types, weeks, strict=True
        )
    ]


def _metric_value(y: Sequence[int], p: Sequence[float], metric: str) -> float:
    scores = score_probabilities(y, p)
    if metric not in scores:
        raise ValueError(f"unknown metric {metric!r}")
    return float(scores[metric])


def _percentile_linear(sorted_samples: Sequence[float], q: float) -> float:
    """Deterministic linear interpolation percentile on a sorted sample."""

    if not sorted_samples:
        raise ValueError("samples required")
    if q <= 0:
        return float(sorted_samples[0])
    if q >= 1:
        return float(sorted_samples[-1])
    n = len(sorted_samples)
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return float(sorted_samples[lo] * (1.0 - frac) + sorted_samples[hi] * frac)


def bootstrap_paired_delta_clusters(
    clusters: Sequence[Any],
    y_true: Sequence[int],
    p_left: Sequence[float],
    p_right: Sequence[float],
    *,
    metric: str = "log_loss",
    n_boot: int = 500,
    seed: int = 20260904,
    contrast_id: str,
) -> dict[str, float | int | str]:
    """Cluster-bootstrap metric(right) - metric(left) with centered null p-value.

    Percentile CI uses uncentered replicate deltas. The two-sided p-value uses
    the centered null ``Δ* - Δ``:
    ``p = (1 + #{|Δ* - Δ| ≥ |Δ|}) / (n_boot + 1)``.
    """

    n = len(y_true)
    if not (n == len(p_left) == len(p_right) == len(clusters)):
        raise ValueError("clusters, y_true, p_left, and p_right must align")
    if n == 0:
        raise ValueError("at least one row is required")
    if n_boot < 1:
        raise ValueError("n_boot must be >= 1")

    by_cluster: dict[Any, list[int]] = {}
    for index, key in enumerate(clusters):
        by_cluster.setdefault(key, []).append(index)
    cluster_ids = sorted(by_cluster, key=lambda c: (str(type(c)), str(c)))
    rng = contrast_rng(seed, contrast_id)

    def delta_for(indices: Sequence[int]) -> float:
        y = [y_true[i] for i in indices]
        left = [p_left[i] for i in indices]
        right = [p_right[i] for i in indices]
        return _metric_value(y, right, metric) - _metric_value(y, left, metric)

    observed = delta_for(range(n))
    samples: list[float] = []
    for _ in range(n_boot):
        drawn = [cluster_ids[rng.randrange(len(cluster_ids))] for _ in cluster_ids]
        indices: list[int] = []
        for key in drawn:
            indices.extend(by_cluster[key])
        samples.append(delta_for(indices))

    ordered = sorted(samples)
    abs_obs = abs(observed)
    extreme = sum(1 for value in samples if abs(value - observed) >= abs_obs - 1e-15)
    p_value = (1 + extreme) / (n_boot + 1)
    return {
        "metric": metric,
        "contrast_id": contrast_id,
        "delta": observed,
        "mean_delta": sum(samples) / len(samples),
        "ci_low": _percentile_linear(ordered, 0.025),
        "ci_high": _percentile_linear(ordered, 0.975),
        "p_value": p_value,
        "n_boot": n_boot,
        "seed": seed,
        "n_clusters": len(cluster_ids),
        "n_rows": n,
    }
