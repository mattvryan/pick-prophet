"""Betting-market transformations with an explicit home-team convention."""

from __future__ import annotations

from collections.abc import Iterable
from statistics import median
from typing import Any


def american_implied_probability(odds: float | None) -> float | None:
    if odds is None or odds == 0:
        return None
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def probability_to_american(probability: float | None) -> float | None:
    if probability is None or not 0 < probability < 1:
        return None
    if probability >= 0.5:
        return -100.0 * probability / (1.0 - probability)
    return 100.0 * (1.0 - probability) / probability


def remove_two_way_vig(
    home_odds: float | None, away_odds: float | None
) -> float | None:
    home = american_implied_probability(home_odds)
    away = american_implied_probability(away_odds)
    if home is None or away is None or home + away == 0:
        return None
    return home / (home + away)


def consensus_line(providers: Iterable[dict[str, Any]]) -> dict[str, Any]:
    providers = list(providers)

    def med(key: str) -> float | None:
        values = [float(row[key]) for row in providers if row.get(key) is not None]
        return median(values) if values else None

    def consensus_moneyline(key: str) -> float | None:
        probabilities = [
            american_implied_probability(row.get(key)) for row in providers
        ]
        available = [value for value in probabilities if value is not None]
        return probability_to_american(median(available)) if available else None

    home_ml = consensus_moneyline("homeMoneyline")
    away_ml = consensus_moneyline("awayMoneyline")
    return {
        "spread_home": med("spread"),
        "total": med("overUnder"),
        "home_moneyline": home_ml,
        "away_moneyline": away_ml,
        "line_provider_count": len(providers),
        "home_implied_prob": remove_two_way_vig(home_ml, away_ml),
    }
