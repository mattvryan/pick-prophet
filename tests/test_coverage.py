"""Coverage auditor tests use tiny synthetic CSVs only."""

from __future__ import annotations

import csv
from pathlib import Path

from pick_prophet.features.coverage import (
    audit_rows,
    audit_season_file,
    render_coverage_report,
    run_coverage,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _base_row(**overrides):
    row = {
        "game_id": "1",
        "season": "2024",
        "week": "1",
        "home_team": "A",
        "away_team": "B",
        "home_team_id": "10",
        "away_team_id": "20",
        "home_points": "21",
        "away_points": "14",
        "home_win": "1",
        "spread_home": "-3.5",
        "home_implied_prob": "0.6",
        "elo_home": "1600",
        "elo_away": "1500",
        "neutral_site": "False",
    }
    row.update({k: str(v) if v is not None else "" for k, v in overrides.items()})
    return row


def test_detects_duplicate_game_ids() -> None:
    rows = [_base_row(game_id=1), _base_row(game_id=1, home_points=7, away_points=0)]
    audit = audit_rows(rows, season=2024)
    check = next(c for c in audit.checks if c.name == "unique_game_id")
    assert check.status == "fail"
    assert audit.status == "fail"


def test_detects_inconsistent_outcomes() -> None:
    rows = [_base_row(home_win=0)]  # points say home won
    audit = audit_rows(rows, season=2024)
    check = next(c for c in audit.checks if c.name == "outcome_consistency")
    assert check.status == "fail"


def test_warns_on_missing_odds() -> None:
    rows = [
        _base_row(
            game_id=i,
            spread_home="",
            home_implied_prob="",
            elo_home="",
            elo_away="",
        )
        for i in range(1, 6)
    ]
    audit = audit_rows(rows, season=2024)
    odds = next(c for c in audit.checks if c.name == "odds_coverage")
    assert odds.status == "fail"
    joint = next(c for c in audit.checks if c.name == "odds_rating_joint_coverage")
    assert joint.status == "fail"


def test_run_coverage_writes_report(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    _write_csv(
        processed / "games_2024.csv",
        [_base_row(game_id=1), _base_row(game_id=2, neutral_site=True)],
    )
    _write_csv(
        processed / "games_2023.csv",
        [_base_row(season=2023, game_id=3, home_points="", away_points="", home_win="")],
    )
    report = tmp_path / "docs" / "data_coverage_report.md"
    summary_json = tmp_path / "docs" / "coverage_summary.json"
    week_csv = tmp_path / "docs" / "coverage_by_week.csv"
    windows_json = tmp_path / "docs" / "coverage_evaluation_windows.json"
    audits, markdown = run_coverage(
        processed,
        report_path=report,
        summary_json=summary_json,
        week_csv=week_csv,
        windows_json=windows_json,
    )
    assert report.exists()
    assert "2023" in markdown and "2024" in markdown
    assert "Recommended evaluation windows" in markdown
    assert len(audits) == 2
    # Incomplete outcomes warn; season still present.
    assert any(a.season == 2023 for a in audits)
    assert (processed / "games_2024.quality.json").exists()
    assert "Cross-season gate" in render_coverage_report(audits)
    assert summary_json.exists() and week_csv.exists() and windows_json.exists()


def test_week_gap_and_structural_fpi(tmp_path: Path) -> None:
    rows = [
        _base_row(game_id=1, week=1, fpi_home="", fpi_away="", sp_home="", sp_away=""),
        _base_row(game_id=2, week=3, fpi_home="", fpi_away="", sp_home="", sp_away=""),
    ]
    # Ensure FPI/SP columns exist as empty structural nulls.
    for row in rows:
        row.setdefault("fpi_home", "")
        row.setdefault("fpi_away", "")
        row.setdefault("sp_home", "")
        row.setdefault("sp_away", "")
    audit = audit_rows(rows, season=2024)
    week_check = next(c for c in audit.checks if c.name == "week_continuity")
    assert week_check.status == "warn"
    fpi = next(c for c in audit.checks if c.name == "fpi_missingness")
    assert fpi.value["class"] == "structural_unjoined"
    assert audit.usable_for["fpi_models"] == "blocked_structural"
    assert audit.week_coverage[0]["week"] == 1
    assert audit.week_coverage[1]["week"] == 3


def test_missing_identity_fails() -> None:
    audit = audit_rows([_base_row(home_team_id="")], season=2024)
    check = next(c for c in audit.checks if c.name == "team_identity")
    assert check.status == "fail"
    assert audit.usable_for["market_baseline"] == "blocked_integrity"


def test_audit_season_file_reads_path(tmp_path: Path) -> None:
    path = tmp_path / "games_2022.csv"
    _write_csv(path, [_base_row(season=2022, game_id=9, line_provider_count=2)])
    audit = audit_season_file(path)
    assert audit.season == 2022
    assert audit.status != "fail"
    assert audit.rows == 1
    assert any(c.name == "unique_game_id" and c.status == "pass" for c in audit.checks)
