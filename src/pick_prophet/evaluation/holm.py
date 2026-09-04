"""Holm–Bonferroni step-down adjustment."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def holm_adjust(
    p_values: Sequence[float | None],
    *,
    alpha: float = 0.05,
) -> list[dict[str, Any]]:
    """Adjust estimable p-values with Holm step-down; skip ``None`` entries.

    Returns one dict per input index. Non-estimable rows keep ``raw_p=None``,
    ``holm_p=None``, ``rank=None``, ``reject=False``, and use the realized
    family size of estimable hypotheses only.
    """

    if alpha <= 0 or alpha >= 1:
        raise ValueError("alpha must be in (0, 1)")

    estimable = [(i, float(p)) for i, p in enumerate(p_values) if p is not None]
    for _, p in estimable:
        if not (0.0 <= p <= 1.0):
            raise ValueError(f"p-value out of [0, 1]: {p}")

    family_size = len(estimable)
    results: list[dict[str, Any]] = [
        {
            "index": i,
            "raw_p": None if p is None else float(p),
            "holm_p": None,
            "rank": None,
            "family_size": family_size,
            "reject": False,
        }
        for i, p in enumerate(p_values)
    ]
    if family_size == 0:
        return results

    ordered = sorted(estimable, key=lambda item: (item[1], item[0]))
    adjusted: dict[int, float] = {}
    running = 0.0
    for rank, (index, p) in enumerate(ordered, start=1):
        m = family_size - rank + 1
        candidate = min(1.0, p * m)
        running = max(running, candidate)
        adjusted[index] = running
        results[index]["rank"] = rank
        results[index]["holm_p"] = running

    # Step-down reject: find largest k with holm_p_(k) <= alpha after ordering
    reject_up_to = 0
    for rank, (index, _) in enumerate(ordered, start=1):
        if adjusted[index] <= alpha:
            reject_up_to = rank
        else:
            break
    for rank, (index, _) in enumerate(ordered, start=1):
        results[index]["reject"] = rank <= reject_up_to

    return results
