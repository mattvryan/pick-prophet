import csv
from pathlib import Path

import pytest

from pick_prophet.research.elo_pregame_vs_weekly import (
    AGGREGATE_COLUMNS,
    DEFAULT_TOLERANCE,
    PERCENTILE_METHOD,
    ConflictError,
    EloKey,
    aggregate_sides,
    compare_snapshot,
    load_games,
    load_weekly_elo,
    sha256_file,
    write_aggregate_csv,
)

FIX = Path(__file__).parent / "fixtures" / "ratings_elo_compare"


def _aggregate_fixture() -> tuple[list[dict], object, list[object], dict]:
    games = load_games(FIX / "games.json")
    weekly = load_weekly_elo(FIX / "elo.json")
    sides = compare_snapshot(games, weekly, tolerance=DEFAULT_TOLERANCE)
    rows = {
        (row["season"], row["season_type"], row["week"]): row
        for row in aggregate_sides(sides)
    }
    return games, weekly, sides, rows


def test_week1_uses_feature_week_zero_and_counts_nulls():
    _, _, sides, rows = _aggregate_fixture()

    week_sides = [
        side
        for side in sides
        if (side.season, side.season_type, side.week) == (2099, "regular", 1)
    ]
    assert {side.feature_week for side in week_sides} == {0}
    assert rows[(2099, "regular", 1)] == {
        "season": 2099,
        "season_type": "regular",
        "week": 1,
        "n_sides": 2,
        "n_both_present": 1,
        "n_exact_match": 1,
        "exact_match_rate": 1.0,
        "n_within_tolerance": 1,
        "within_tolerance_rate": 1.0,
        "mean_abs_delta": 0.0,
        "median_abs_delta": 0.0,
        "p90_abs_delta": 0.0,
        "p95_abs_delta": 0.0,
        "max_abs_delta": 0.0,
        "n_pregame_null": 1,
        "pregame_null_rate": 0.5,
        "n_weekly_null": 0,
        "weekly_null_rate": 0.0,
        "n_pregame_only": 0,
        "n_weekly_only": 1,
        "n_name_fallback_joins": 2,
    }


def test_midseason_exact_vs_tolerance_metrics():
    *_, rows = _aggregate_fixture()

    row = rows[(2099, "regular", 5)]
    assert row["n_both_present"] == 2
    assert row["n_exact_match"] == 1
    assert row["exact_match_rate"] == 0.5
    assert row["n_within_tolerance"] == 1
    assert row["within_tolerance_rate"] == 0.5
    assert row["mean_abs_delta"] == 2.5
    assert row["median_abs_delta"] == 2.5
    assert row["p90_abs_delta"] == 5.0
    assert row["p95_abs_delta"] == 5.0
    assert row["max_abs_delta"] == 5.0
    assert PERCENTILE_METHOD == "sorted_index"


def test_postseason_isolated_from_regular_week_numbers():
    *_, rows = _aggregate_fixture()

    row = rows[(2099, "postseason", 1)]
    assert row["n_both_present"] == 0
    assert row["n_weekly_null"] == 2
    assert row["n_pregame_only"] == 2
    assert row["mean_abs_delta"] is None
    assert row["exact_match_rate"] is None


def test_multi_season_isolation():
    *_, rows = _aggregate_fixture()

    row = rows[(2098, "regular", 3)]
    assert row["n_both_present"] == 2
    assert row["n_exact_match"] == 1
    assert row["max_abs_delta"] == 2.0


def test_identical_duplicates_deduped_with_audit():
    weekly = load_weekly_elo(FIX / "elo.json")

    assert weekly.identical_duplicate_count == 1
    assert weekly[EloKey(2099, "regular", 0, "name", "Alpha")] == pytest.approx(1500)


def test_conflicting_duplicates_raise():
    with pytest.raises(ConflictError, match="Conflict Team"):
        load_weekly_elo(FIX / "elo_conflict.json")


def test_fbs_filter_skips_lower_division_only():
    games = load_games(FIX / "games.json")

    assert len(games) == 4
    assert {game["game_id"] for game in games} == {1, 2, 3, 4}


def test_snake_case_payload_and_id_join_are_supported(tmp_path):
    games_path = tmp_path / "games.json"
    games_path.write_text(
        """[{"id": 9, "season": 2099, "week": 2, "season_type": "regular",
        "start_date": "2099-09-05T16:00:00Z", "home_id": 901, "away_id": 902,
        "home_team": "ID Home", "away_team": "Missing Away",
        "home_classification": "fbs", "away_classification": "fcs",
        "home_pregame_elo": 1525, "away_pregame_elo": 1475}]"""
    )
    elo_path = tmp_path / "elo.json"
    elo_path.write_text(
        """[{"year": 2099, "season_type": "regular", "week": 1,
        "team_id": 901, "team": "Wrong Name Is Irrelevant", "elo": 1525}]"""
    )

    sides = compare_snapshot(
        load_games(games_path),
        load_weekly_elo(elo_path),
        tolerance=DEFAULT_TOLERANCE,
    )

    assert sides[0].join_key_type == "id"
    assert sides[0].weekly_elo == pytest.approx(1525)
    assert sides[1].weekly_elo is None


def test_write_aggregate_csv_uses_exact_header_and_hashes_output(tmp_path):
    *_, rows_by_key = _aggregate_fixture()
    rows = list(rows_by_key.values())
    output = tmp_path / "aggregate.csv"

    write_aggregate_csv(rows, output)

    with output.open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(AGGREGATE_COLUMNS)
        assert len(list(reader)) == 4
    assert len(sha256_file(output)) == 64
