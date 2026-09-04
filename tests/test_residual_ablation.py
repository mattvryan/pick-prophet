"""Integration tests for M10 ablation runner."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pick_prophet.cli import parser
from pick_prophet.models.fixed_offset_logit import sigmoid
from pick_prophet.models.residual_ablation import run_ablation, season_drop_metrics
from pick_prophet.models.residual_ablation_variants import MIN_ESPN_N


def _base_row(
    game_id: int,
    season: int,
    *,
    week: int = 2,
    logit: float = 0.0,
    y: int = 1,
    conference: str = "A",
    spread: float | None = -3.0,
    sampling_frame: str = "all_fbs",
    helpful: float = 0.0,
    noise: float = 0.0,
    single_season: float = 0.0,
) -> dict[str, str]:
    prob = float(sigmoid(logit))
    return {
        "game_id": str(game_id),
        "season": str(season),
        "week": str(week),
        "season_type": "regular",
        "kickoff_utc": f"{season}-09-0{min(week, 9)}T18:00:00+00:00",
        "home_team_id": "1",
        "away_team_id": "2",
        "home_team": "H",
        "away_team": "A",
        "home_win": str(y),
        "home_implied_prob": str(prob),
        "home_market_logit": str(logit),
        "home_conference": conference,
        "away_conference": "B",
        "home_classification": "fbs",
        "away_classification": "fbs",
        "neutral_site": "true" if week == 4 else "false",
        "home_field_advantage": "0" if week == 4 else "1",
        "is_week_1": "true" if week == 1 else "false",
        "is_weeks_1_3": "true" if week <= 3 else "false",
        "spread_home": "" if spread is None else str(spread),
        "total": "50",
        "home_moneyline": "-150",
        "away_moneyline": "130",
        "line_provider_count": "3",
        "spread_home_open": "",
        "total_open": "",
        "spread_move_home": "",
        "total_move": "",
        "home_entering_wins": "1",
        "home_entering_losses": "0",
        "away_entering_wins": "0",
        "away_entering_losses": "1",
        "home_previous_result": "1",
        "away_previous_result": "0",
        "home_sos": "0.5",
        "away_sos": "0.4",
        "home_days_rest": "7",
        "away_days_rest": "7",
        "sampling_frame": sampling_frame,
        "source_snapshot": "snap",
        "synth_helpful": str(helpful),
        "synth_noise": str(noise),
        "synth_single_season": str(single_season),
    }


def _write_matrix(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _synth_matrix(path: Path) -> None:
    rows: list[dict[str, str]] = []
    gid = 1
    for season in (2017, 2018, 2019, 2020):
        for week in (1, 2, 4):
            for i in range(4):
                y = 1 if i % 2 == 0 else 0
                helpful = 1.5 if y == 1 else -1.5
                noise = ((gid * 17) % 7) / 10.0
                single = (2.0 if y == 1 else -2.0) if season == 2020 else 0.0
                logit = 0.1 if y == 1 else -0.1
                # Keep verified-ESPN count small but present in held-out seasons
                frame = (
                    "verified_espn_pickem"
                    if season >= 2018 and i == 0 and week == 1
                    else "all_fbs"
                )
                rows.append(
                    _base_row(
                        gid,
                        season,
                        week=week,
                        logit=logit,
                        y=y,
                        conference="SEC" if i == 0 else "B1G",
                        sampling_frame=frame,
                        helpful=helpful,
                        noise=noise,
                        single_season=single,
                    )
                )
                gid += 1
    _write_matrix(path, rows)


def _tiny_variants() -> dict[str, tuple[str, ...]]:
    return {
        "market_only": (),
        "single__synth_helpful": ("synth_helpful",),
        "single__synth_noise": ("synth_noise",),
        "single__synth_single_season": ("synth_single_season",),
        "single__home_conference": ("home_conference",),
        "family__site_temporal": (
            "home_field_advantage",
            "is_week_1",
            "is_weeks_1_3",
            "home_conference",
            "away_conference",
            "home_classification",
            "away_classification",
        ),
        "combined": (
            "home_field_advantage",
            "is_week_1",
            "is_weeks_1_3",
            "home_conference",
            "away_conference",
            "home_classification",
            "away_classification",
            "synth_helpful",
        ),
        "lof__without_site_temporal": ("synth_helpful",),
    }


def test_run_ablation_core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import pick_prophet.models.residual_ablation as abl

    monkeypatch.setattr(abl, "assert_ablation_variants_valid", lambda variants=None: None)

    matrix = tmp_path / "matrix.csv"
    _synth_matrix(matrix)
    out = tmp_path / "ablation"
    paths = run_ablation(
        matrix,
        out,
        variants=_tiny_variants(),
        n_boot=20,
        write_report_path=tmp_path / "report.md",
    )
    worksheet = list(csv.DictReader(paths["decision_worksheet"].open()))
    assert worksheet
    assert all(row["recommendation"] == "" for row in worksheet)

    overall = {r["variant"]: r for r in csv.DictReader(paths["overall_metrics"].open())}
    assert float(overall["single__synth_helpful"]["delta_log_loss"]) < 0

    drops = [
        r
        for r in csv.DictReader(paths["season_drop"].open())
        if r["variant"] == "single__synth_single_season"
    ]
    drop_2020 = next(r for r in drops if r["drop_season"] == "2020")
    full_ll = float(overall["single__synth_single_season"]["delta_log_loss"])
    assert drop_2020["retrain"] == "False"
    assert drop_2020["mode"] == "aggregate_existing_predictions"
    if drop_2020["status"] == "ok":
        assert float(drop_2020["delta_log_loss"]) > full_ll - 1e-9 or abs(
            float(drop_2020["delta_log_loss"])
        ) < abs(full_ll)

    espn = [
        r
        for r in csv.DictReader(paths["slice_metrics"].open())
        if r["slice"] == "verified_espn_pickem"
    ]
    assert espn
    assert any(r["status"] == "insufficient" for r in espn)
    for r in espn:
        if r["status"] == "insufficient":
            assert int(r["n"]) < MIN_ESPN_N
            assert r["delta_log_loss"] == ""

    reg = (out / "compact" / "ablation_registry.json").read_text()
    assert "single__home_conference" in reg
    assert "home_conference=SEC" not in reg


def test_identical_ids_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import pick_prophet.models.residual_ablation as abl

    monkeypatch.setattr(abl, "assert_ablation_variants_valid", lambda variants=None: None)
    matrix = tmp_path / "matrix.csv"
    _synth_matrix(matrix)
    out = tmp_path / "ablation"
    run_ablation(matrix, out, variants=_tiny_variants(), n_boot=5)
    preds = list(csv.DictReader((out / "fit" / "predictions.csv").open()))
    by_model: dict[str, set[tuple[str, str]]] = {}
    for row in preds:
        by_model.setdefault(row["model"], set()).add((row["fold_id"], row["game_id"]))
    market = by_model["market_only"]
    for model, ids in by_model.items():
        assert ids == market, model


def test_season_drop_deterministic() -> None:
    paired = [
        {
            "test_season": 2018,
            "y_true": 1,
            "p_candidate": 0.8,
            "p_market": 0.6,
        },
        {
            "test_season": 2019,
            "y_true": 0,
            "p_candidate": 0.3,
            "p_market": 0.4,
        },
        {
            "test_season": 2020,
            "y_true": 1,
            "p_candidate": 0.9,
            "p_market": 0.5,
        },
    ]
    a = season_drop_metrics(paired, drop_season=2020)
    b = season_drop_metrics(paired, drop_season=2020)
    assert a == b
    assert a["retrain"] is False
    assert a["n"] == 2


def test_cli_wiring() -> None:
    args = parser().parse_args(
        [
            "ablate-residual",
            "--matrix",
            "m.csv",
            "--out-dir",
            "out",
        ]
    )
    assert args.command == "ablate-residual"
