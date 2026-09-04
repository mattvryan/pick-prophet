"""Tests for Holm–Bonferroni adjustment."""

from __future__ import annotations

from pick_prophet.evaluation.holm import holm_adjust


def test_holm_ordering_and_rejection() -> None:
    rows = holm_adjust([0.01, 0.04, 0.03, None], alpha=0.05)
    assert rows[3]["raw_p"] is None
    assert rows[3]["family_size"] == 3
    assert rows[3]["reject"] is False

    # Sorted raw: 0.01, 0.03, 0.04 → multipliers 3,2,1
    by_index = {r["index"]: r for r in rows}
    assert by_index[0]["rank"] == 1
    assert by_index[0]["holm_p"] == 0.03  # 0.01 * 3
    assert by_index[2]["rank"] == 2
    assert abs(by_index[2]["holm_p"] - 0.06) < 1e-12  # max(0.03, 0.03*2)
    assert by_index[1]["rank"] == 3
    assert abs(by_index[1]["holm_p"] - 0.06) < 1e-12  # max(0.06, 0.04)
    assert by_index[0]["reject"] is True
    assert by_index[2]["reject"] is False
    assert by_index[1]["reject"] is False


def test_holm_empty_family() -> None:
    rows = holm_adjust([None, None])
    assert all(r["family_size"] == 0 and r["holm_p"] is None for r in rows)
