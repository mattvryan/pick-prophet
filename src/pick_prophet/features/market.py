"""Betting-market transformations with an explicit home-team convention."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import median
from typing import Any

# Clip logits so extreme prices remain finite for logistic models.
DEFAULT_LOGIT_BOUND = 10.0

MARKET_TIMING_CFBD_HISTORICAL = (
    "cfbd_historical_closing_like_no_observation_timestamp"
)
MARKET_TIMING_POINT_IN_TIME = "point_in_time_filtered_by_observed_at"


@dataclass(frozen=True)
class ProviderLineObservation:
    """One provider quote for a game.

    Operational meanings:
    - ``observed_at``: when the quote was captured. Required to order opening /
      latest-prelock / closing. Absent on current CFBD historical `/lines`
      payloads, so open/close *order* must not be inferred from list order.
    - ``spread_open`` / ``total_open``: provider-labeled opening values when the
      source exposes them as fields (not inferred).
    - Closing-like consensus without timestamps is labelled
      ``cfbd_historical_closing_like_no_observation_timestamp``.
    """

    provider: str | None
    spread: float | None
    total: float | None
    home_moneyline: float | None
    away_moneyline: float | None
    spread_open: float | None = None
    total_open: float | None = None
    observed_at: str | None = None
    as_of_role: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def american_implied_probability(odds: float | None) -> float | None:
    if odds is None or odds == 0:
        return None
    odds = float(odds)
    # American odds are discontinuous at 0; zero is rejected above.
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


def market_logit(
    probability: float | None,
    *,
    bound: float = DEFAULT_LOGIT_BOUND,
) -> float | None:
    """Bounded logit of a vig-removed home win probability."""

    if probability is None:
        return None
    p = min(max(float(probability), 1e-15), 1 - 1e-15)
    value = math.log(p / (1 - p))
    return min(max(value, -bound), bound)


def parse_provider_line(raw: dict[str, Any]) -> ProviderLineObservation:
    """Normalize camelCase/snake_case CFBD (or manual) provider rows."""

    return ProviderLineObservation(
        provider=raw.get("provider"),
        spread=_to_float(raw.get("spread")),
        total=_to_float(raw.get("overUnder", raw.get("over_under", raw.get("total")))),
        home_moneyline=_to_float(
            raw.get("homeMoneyline", raw.get("home_moneyline"))
        ),
        away_moneyline=_to_float(
            raw.get("awayMoneyline", raw.get("away_moneyline"))
        ),
        spread_open=_to_float(raw.get("spreadOpen", raw.get("spread_open"))),
        total_open=_to_float(
            raw.get("overUnderOpen", raw.get("over_under_open", raw.get("total_open")))
        ),
        observed_at=raw.get("observedAt", raw.get("observed_at")),
        as_of_role=str(raw.get("as_of_role", raw.get("asOfRole", "unknown"))),
    )


def filter_observations_before_kickoff(
    observations: Sequence[ProviderLineObservation],
    kickoff_utc: str | None,
) -> tuple[list[ProviderLineObservation], list[ProviderLineObservation]]:
    """Keep quotes at/before kickoff when ``observed_at`` is present.

    Observations without timestamps are retained (CFBD historical case) but
    callers must not treat list order as time order. Post-kick quotes are
    returned separately for audit.
    """

    kickoff = _parse_timestamp(kickoff_utc)
    kept: list[ProviderLineObservation] = []
    rejected: list[ProviderLineObservation] = []
    for obs in observations:
        observed = _parse_timestamp(obs.observed_at)
        if kickoff is None or observed is None:
            kept.append(obs)
            continue
        if observed <= kickoff:
            kept.append(obs)
        else:
            rejected.append(obs)
    return kept, rejected


def _median_float(values: Iterable[float | None]) -> float | None:
    available = [float(v) for v in values if v is not None]
    return median(available) if available else None


def consensus_moneyline_from_probs(
    moneylines: Iterable[float | None],
) -> float | None:
    """Median American odds via implied probabilities (never raw ML average)."""

    probabilities = [american_implied_probability(ml) for ml in moneylines]
    available = [p for p in probabilities if p is not None]
    return probability_to_american(median(available)) if available else None


def line_movement(
    opening: float | None, closing: float | None
) -> float | None:
    """Closing minus opening when both labeled values exist."""

    if opening is None or closing is None:
        return None
    return float(closing) - float(opening)


def consensus_line(
    providers: Iterable[dict[str, Any]],
    *,
    kickoff_utc: str | None = None,
    logit_bound: float = DEFAULT_LOGIT_BOUND,
) -> dict[str, Any]:
    """Build consensus market features for one game.

    Never fabricates moneyline probabilities from spread/total. When provider
    observation timestamps are missing, timing is labelled closing-like and
    opening fields are used only when the source supplies ``spreadOpen`` /
    ``overUnderOpen``.
    """

    raw_list = list(providers)
    observations = [parse_provider_line(row) for row in raw_list]
    kept, rejected = filter_observations_before_kickoff(observations, kickoff_utc)
    has_timestamps = any(obs.observed_at for obs in observations)
    timing = (
        MARKET_TIMING_POINT_IN_TIME if has_timestamps else MARKET_TIMING_CFBD_HISTORICAL
    )

    home_ml = consensus_moneyline_from_probs(obs.home_moneyline for obs in kept)
    away_ml = consensus_moneyline_from_probs(obs.away_moneyline for obs in kept)
    implied = remove_two_way_vig(home_ml, away_ml)
    spread_home = _median_float(obs.spread for obs in kept)
    total = _median_float(obs.total for obs in kept)
    spread_open = _median_float(obs.spread_open for obs in kept)
    total_open = _median_float(obs.total_open for obs in kept)

    return {
        "spread_home": spread_home,
        "total": total,
        "home_moneyline": home_ml,
        "away_moneyline": away_ml,
        "line_provider_count": len(kept),
        "home_implied_prob": implied,
        "home_market_logit": market_logit(implied, bound=logit_bound),
        "spread_home_open": spread_open,
        "total_open": total_open,
        "spread_move_home": line_movement(spread_open, spread_home),
        "total_move": line_movement(total_open, total),
        "market_timing": timing,
        "post_kick_provider_quotes_rejected": len(rejected),
        # Explicit: spread never fills moneyline probability.
        "moneyline_fabricated_from_spread": False,
    }


def provider_coverage_rows(
    game_line_payloads: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize provider presence by season/week for coverage reports."""

    buckets: dict[tuple[Any, Any, str], int] = {}
    for game in game_line_payloads:
        season = game.get("season")
        week = game.get("week")
        for raw in game.get("lines") or []:
            obs = parse_provider_line(raw)
            provider = obs.provider or "unknown"
            key = (season, week, provider)
            buckets[key] = buckets.get(key, 0) + 1
    rows = [
        {
            "season": season,
            "week": week,
            "provider": provider,
            "quote_count": count,
        }
        for (season, week, provider), count in sorted(
            buckets.items(), key=lambda item: (str(item[0][0]), str(item[0][1]), item[0][2])
        )
    ]
    return rows
