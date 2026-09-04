"""M08 residual model variant column registries."""

from __future__ import annotations

from pick_prophet.features.matrix_schema import MODEL_FEATURE_COLUMNS

SITE_TEMPORAL_COLUMNS: tuple[str, ...] = (
    "home_field_advantage",
    "is_week_1",
    "is_weeks_1_3",
    "home_conference",
    "away_conference",
    "home_classification",
    "away_classification",
)

HISTORY_COLUMNS: tuple[str, ...] = (
    "home_entering_wins",
    "home_entering_losses",
    "away_entering_wins",
    "away_entering_losses",
    "home_previous_result",
    "away_previous_result",
    "home_sos",
    "away_sos",
    "home_days_rest",
    "away_days_rest",
)

MARKET_CONTEXT_COLUMNS: tuple[str, ...] = (
    "spread_home",
    "total",
    "line_provider_count",
    "spread_home_open",
    "total_open",
    "spread_move_home",
    "total_move",
)

COMBINED_COLUMNS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (*SITE_TEMPORAL_COLUMNS, *HISTORY_COLUMNS, *MARKET_CONTEXT_COLUMNS)
    )
)

VARIANTS: dict[str, tuple[str, ...]] = {
    "market_only": (),
    "site_temporal": SITE_TEMPORAL_COLUMNS,
    "history": HISTORY_COLUMNS,
    "market_context": MARKET_CONTEXT_COLUMNS,
    "combined": COMBINED_COLUMNS,
}

PROHIBITED_ADJUSTMENT_EXACT: frozenset[str] = frozenset(
    {
        "home_market_logit",
        "home_implied_prob",
        "home_moneyline",
        "away_moneyline",
        "neutral_site",
        "home_win",
        "game_id",
        "elo_home",
        "elo_away",
        "espn_home_pick_pct",
        "espn_expert_home_pct",
    }
)


def assert_variants_valid() -> None:
    allowed = set(MODEL_FEATURE_COLUMNS)
    for name, columns in VARIANTS.items():
        for col in columns:
            if col not in allowed:
                raise ValueError(
                    f"variant {name}: column {col!r} not in MODEL_FEATURE_COLUMNS"
                )
            if col in PROHIBITED_ADJUSTMENT_EXACT:
                raise ValueError(
                    f"variant {name}: prohibited adjustment column {col!r}"
                )
            if col.startswith(("elo_", "fpi_")) or (
                col.startswith("sp_") and not col.startswith("spread_")
            ):
                raise ValueError(f"variant {name}: deferred rating column {col!r}")
