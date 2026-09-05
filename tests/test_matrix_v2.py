from __future__ import annotations

import pytest

from pick_prophet.features.matrix_v2 import (
    MATRIX_SCHEMA_VERSION,
    build_matrix_v2_rows,
)


def _base(game_id: int = 1, season: int = 2025) -> dict:
    return {"game_id": game_id, "season": season, "home_win": 1}


def test_join_preserves_unknown_and_adds_knownness() -> None:
    form = {
        "game_id": 1,
        "season": 2025,
        "prior_games_home": 1,
        "prior_games_away": 0,
        "form_offense_ppa_diff": None,
    }
    coaching = {
        "game_id": 1,
        "season": 2025,
        "opening_coach_tenure_seasons_diff": "",
        "opening_first_year_coach_diff": "",
    }
    row = build_matrix_v2_rows([_base()], [form], [coaching])[0]
    assert MATRIX_SCHEMA_VERSION == "2.0.0"
    assert row["form_offense_ppa_diff"] is None
    assert row["coaching_context_known"] == 0


def test_join_requires_exact_ids() -> None:
    with pytest.raises(ValueError, match="exactly match"):
        build_matrix_v2_rows([_base()], [], [])


def test_2026_outcomes_are_locked() -> None:
    row = _base(season=2026)
    family = {"game_id": 1, "season": 2026}
    with pytest.raises(ValueError, match="2026 rows are locked"):
        build_matrix_v2_rows([row], [family], [family])
