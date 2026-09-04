"""Tests for M09 cluster-key paired bootstrap."""

from __future__ import annotations

from pick_prophet.evaluation.cluster_bootstrap import (
    bootstrap_paired_delta_clusters,
    cluster_keys,
    contrast_rng,
)


def test_contrast_rng_stable_and_distinct() -> None:
    a1 = contrast_rng(20260904, "combined|overall|log_loss")
    a2 = contrast_rng(20260904, "combined|overall|log_loss")
    b = contrast_rng(20260904, "history|overall|log_loss")
    assert [a1.random() for _ in range(5)] == [a2.random() for _ in range(5)]
    a3 = contrast_rng(20260904, "combined|overall|log_loss")
    assert [a3.random() for _ in range(3)] != [b.random() for _ in range(3)]


def test_cluster_keys_distinguish_seasons_with_same_week() -> None:
    keys = cluster_keys(
        [2018, 2019],
        ["regular", "regular"],
        [1, 1],
    )
    assert keys[0] != keys[1]
    assert keys[0] == (2018, "regular", 1)


def test_bootstrap_pairs_same_indices_for_both_arms() -> None:
    # Identical arms => delta always 0 regardless of resampling.
    clusters = [(2018, "regular", 1), (2018, "regular", 2), (2019, "regular", 1)]
    y = [1, 0, 1]
    p = [0.7, 0.4, 0.6]
    out = bootstrap_paired_delta_clusters(
        clusters,
        y,
        p,
        p,
        metric="log_loss",
        n_boot=50,
        seed=20260904,
        contrast_id="identical|overall|log_loss",
    )
    assert out["delta"] == 0.0
    assert out["ci_low"] == 0.0
    assert out["ci_high"] == 0.0
    assert out["n_clusters"] == 3


def test_bootstrap_deterministic_for_contrast() -> None:
    clusters = [(2018, "regular", 1), (2018, "regular", 2), (2019, "regular", 1)] * 2
    y = [1, 0, 1, 0, 1, 0]
    left = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    right = [0.8, 0.2, 0.7, 0.3, 0.9, 0.1]
    kwargs = dict(
        clusters=clusters,
        y_true=y,
        p_left=left,
        p_right=right,
        metric="brier",
        n_boot=40,
        seed=20260904,
        contrast_id="cand|week_1|brier",
    )
    a = bootstrap_paired_delta_clusters(**kwargs)
    b = bootstrap_paired_delta_clusters(**kwargs)
    assert a == b
    other = bootstrap_paired_delta_clusters(
        **{**kwargs, "contrast_id": "cand|neutral_site|brier"}
    )
    assert (a["ci_low"], a["ci_high"], a["p_value"]) != (
        other["ci_low"],
        other["ci_high"],
        other["p_value"],
    )


def test_centered_p_and_percentile_on_hand_fixture() -> None:
    # One cluster improvement, one cluster degradation — resampling changes Δ*.
    clusters = [(2018, "regular", 1), (2018, "regular", 1), (2019, "regular", 2)]
    y = [1, 1, 0]
    left = [0.6, 0.6, 0.4]
    right = [0.9, 0.9, 0.1]
    out = bootstrap_paired_delta_clusters(
        clusters,
        y,
        left,
        right,
        metric="log_loss",
        n_boot=20,
        seed=20260904,
        contrast_id="hand|overall|log_loss",
    )
    assert out["n_clusters"] == 2
    assert out["n_rows"] == 3
    assert 0.0 < float(out["p_value"]) <= 1.0
    assert float(out["ci_low"]) <= float(out["mean_delta"]) + 1e-12
    assert float(out["mean_delta"]) <= float(out["ci_high"]) + 1e-12
