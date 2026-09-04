"""M07 matrix schema: role allowlists and exclusion gates."""

from __future__ import annotations

from collections.abc import Iterable

MATRIX_SCHEMA_VERSION = "1.0.0"

IDENTIFIER_COLUMNS: tuple[str, ...] = (
    "game_id",
    "season",
    "week",
    "season_type",
    "kickoff_utc",
    "home_team_id",
    "away_team_id",
    "home_team",
    "away_team",
)

TARGET_COLUMNS: tuple[str, ...] = ("home_win",)

BASELINE_INPUT_COLUMNS: tuple[str, ...] = (
    "home_implied_prob",
    "home_market_logit",
)

MODEL_FEATURE_COLUMNS: tuple[str, ...] = (
    # site / conference
    "home_conference",
    "away_conference",
    "home_classification",
    "away_classification",
    "neutral_site",
    "home_field_advantage",
    # temporal
    "is_week_1",
    "is_weeks_1_3",
    # market context
    "spread_home",
    "total",
    "home_moneyline",
    "away_moneyline",
    "line_provider_count",
    "spread_home_open",
    "total_open",
    "spread_move_home",
    "total_move",
    # history
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

AUDIT_SLICE_COLUMNS: tuple[str, ...] = (
    "source_snapshot",
    "market_timing",
    "post_kick_provider_quotes_rejected",
    "moneyline_fabricated_from_spread",
    "sampling_frame",
    "verification_status",
    "match_status",
    "is_pickem_game",
    "espn_home_pick_pct",
    "espn_expert_home_pct",
)

MATRIX_COLUMNS: tuple[str, ...] = (
    *IDENTIFIER_COLUMNS,
    *TARGET_COLUMNS,
    *BASELINE_INPUT_COLUMNS,
    *MODEL_FEATURE_COLUMNS,
    *AUDIT_SLICE_COLUMNS,
)

_ROLE_LISTS: tuple[tuple[str, ...], ...] = (
    IDENTIFIER_COLUMNS,
    TARGET_COLUMNS,
    BASELINE_INPUT_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    AUDIT_SLICE_COLUMNS,
)

FORBIDDEN_EXACT: frozenset[str] = frozenset(
    {
        "elo_home",
        "elo_away",
        "fpi_home",
        "fpi_away",
        "sp_home",
        "sp_away",
    }
)

def assert_roles_disjoint() -> None:
    seen: dict[str, str] = {}
    names = (
        "IDENTIFIER_COLUMNS",
        "TARGET_COLUMNS",
        "BASELINE_INPUT_COLUMNS",
        "MODEL_FEATURE_COLUMNS",
        "AUDIT_SLICE_COLUMNS",
    )
    for name, columns in zip(names, _ROLE_LISTS, strict=True):
        for col in columns:
            if col in seen:
                raise ValueError(
                    f"column {col!r} appears in both {seen[col]} and {name}"
                )
            seen[col] = name


def assert_no_deferred_ratings(columns: Iterable[str]) -> None:
    for col in columns:
        lower = col.lower()
        if col in FORBIDDEN_EXACT or lower in {c.lower() for c in FORBIDDEN_EXACT}:
            raise ValueError(f"deferred rating column forbidden: {col}")
        if (
            lower.startswith(("elo_", "fpi_", "ap_", "coaches_", "cfp_"))
            or (lower.startswith("sp_") and not lower.startswith("spread_"))
            or "vs_market" in lower
            or "rating_disagreement" in lower
        ):
            raise ValueError(f"deferred rating column forbidden: {col}")


def m08_baseline_columns() -> tuple[str, ...]:
    return BASELINE_INPUT_COLUMNS


def m08_predictor_columns() -> tuple[str, ...]:
    return MODEL_FEATURE_COLUMNS
