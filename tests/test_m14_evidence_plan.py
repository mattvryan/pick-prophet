from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pick_prophet.evaluation.protocol import load_protocol
from pick_prophet.research.m14_evidence_plan import (
    build_power_rows,
    generate_m14_artifacts,
)


def test_protocol_2_freezes_2026_as_prospective_only() -> None:
    protocol = load_protocol("2.0.0")
    assert protocol.research_seasons == tuple(range(2017, 2026))
    assert 2026 not in protocol.test_seasons
    assert protocol.prospective_holdout == "2026_weekly_shadow_locked"
    assert protocol.n_boot == 2000


def test_power_rows_are_planning_only() -> None:
    rows = build_power_rows(
        [
            {
                "variant": "family__history",
                "slice": "overall",
                "metric": "log_loss",
                "delta": "-0.001",
                "ci_low": "-0.003",
                "ci_high": "0.001",
                "n_rows": "3195",
                "n_clusters": "66",
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["approx_current_mde_80pct_two_sided"] > 0
    assert (
        rows[0]["approx_mde_at_6000_games"]
        < rows[0]["approx_current_mde_80pct_two_sided"]
    )
    assert rows[0]["interpretation"] == "planning_approximation_not_promotion_evidence"


def test_generate_is_deterministic_and_excludes_2026(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    first = generate_m14_artifacts(repo, tmp_path / "one")
    second = generate_m14_artifacts(repo, tmp_path / "two")
    for name in first:
        assert first[name].read_bytes() == second[name].read_bytes()
    manifest = json.loads(first["manifest"].read_text())
    summary = json.loads(first["summary"].read_text())
    assert manifest["contains_2026_outcomes"] is False
    assert summary["prospective_holdout"] == "2026_weekly_shadow_locked"
    with first["power"].open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 10


def test_unexpected_m10_status_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    m10 = repo / "docs/modeling_artifacts/m10/1.0.0"
    m10.mkdir(parents=True)
    (m10 / "manifest.json").write_text('{"inference_seasons":[2022,2023,2024,2025]}')
    (m10 / "approved_feature_set.json").write_text('{"status":"promoted"}')
    (m10 / "paired_bootstrap.csv").write_text("variant,slice,metric\n")
    (repo / "docs/pickem_inventory.md").write_text("none")
    (repo / "docs/ratings_feasibility.md").write_text("none")
    (repo / "docs/research_protocol_2.md").write_text("frozen")
    (repo / "docs/experiment_ledger_2.json").write_text('{"status":"frozen"}')
    with pytest.raises(ValueError, match="unexpected M10 disposition"):
        generate_m14_artifacts(repo, tmp_path / "out")
