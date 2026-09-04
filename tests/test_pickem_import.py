"""Tests for Pick'em import validation and weekly slate conversion."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pick_prophet.evaluation.artifacts import sampling_frame_for_row
from pick_prophet.features.pickem import (
    REQUIRED_COLUMNS,
    import_pickem_file,
    slate_to_template_rows,
    validate_pickem_import,
    write_template_csv,
)
from pick_prophet.features.pickem_registry import (
    SAMPLING_ALL_FBS,
    SAMPLING_VERIFIED,
    apply_registry_labels,
    build_registry,
    sampling_frame_label,
    unrecoverable_weeks_report,
    write_registry,
)


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "game_id": "401000001",
        "season": "2025",
        "week": "1",
        "display_order": "1",
        "is_pickem_game": "true",
        "espn_home_pick_pct": "55",
        "espn_expert_home_pct": "",
        "pct_captured_at": "2025-08-25T12:00:00Z",
        "captured_at": "2025-08-25T12:00:00Z",
        "source_url": "https://example.invalid/pickem",
        "source_sha256": "",
        "tiebreaker_game_id": "",
        "espn_game_id": "",
        "match_status": "exact_id",
        "verification_status": "unverified",
        "verifier_1": "",
        "verifier_2": "",
    }
    base.update(overrides)
    return base


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    write_template_csv(rows, path)


def test_validate_accepts_template_shaped_fixture(tmp_path: Path) -> None:
    path = tmp_path / "ok.csv"
    _write(path, [_row()])
    result = validate_pickem_import(path)
    assert result.ok
    assert len(result.rows) == 1


def test_confirmed_requires_two_distinct_verifiers(tmp_path: Path) -> None:
    path = tmp_path / "confirmed.csv"
    _write(
        path,
        [
            _row(
                verification_status="confirmed",
                verifier_1="alice",
                verifier_2="alice",
            )
        ],
    )
    result = validate_pickem_import(path)
    assert not result.ok
    assert any("two distinct verifiers" in e for e in result.errors)

    _write(
        path,
        [
            _row(
                verification_status="confirmed",
                verifier_1="alice",
                verifier_2="bob",
                source_sha256="a" * 64,
            )
        ],
    )
    assert validate_pickem_import(path).ok


def test_duplicate_display_order_fails(tmp_path: Path) -> None:
    path = tmp_path / "dup.csv"
    _write(
        path,
        [
            _row(game_id="1", display_order="1"),
            _row(game_id="2", display_order="1"),
        ],
    )
    result = validate_pickem_import(path)
    assert not result.ok
    assert any("duplicate display_order" in e for e in result.errors)


def test_confirmed_rejects_fallback_match(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    _write(
        path,
        [
            _row(
                verification_status="confirmed",
                verifier_1="a",
                verifier_2="b",
                match_status="fallback_review",
                source_sha256="b" * 64,
            )
        ],
    )
    result = validate_pickem_import(path)
    assert not result.ok


def test_missing_provenance_fails(tmp_path: Path) -> None:
    path = tmp_path / "noprov.csv"
    _write(path, [_row(captured_at="", source_url="")])
    result = validate_pickem_import(path)
    assert not result.ok
    assert any("captured_at" in e for e in result.errors)
    assert any("source_url" in e for e in result.errors)


def test_unmatched_game_id_warns(tmp_path: Path) -> None:
    path = tmp_path / "unknown.csv"
    _write(path, [_row(game_id="999")])
    result = validate_pickem_import(path, known_game_ids={1, 2, 3})
    assert result.ok
    assert any("not found in known game set" in w for w in result.warnings)
    assert result.rows[0]["match_status"] == "unmatched"


def test_import_copies_after_validation(tmp_path: Path) -> None:
    src = tmp_path / "src.csv"
    dest = tmp_path / "external" / "pickem_2025_w1.csv"
    _write(src, [_row()])
    assert import_pickem_file(src, dest) == dest
    assert dest.exists()
    with pytest.raises(FileExistsError):
        import_pickem_file(src, dest)


def test_slate_to_template_rows_maps_weekly_fields(tmp_path: Path) -> None:
    slate = tmp_path / "slate.csv"
    with slate.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "display_order",
                "season",
                "contest_week",
                "cfbd_game_id",
                "home_public_pick_pct",
                "captured_at_utc",
                "source",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "display_order": "1",
                "season": "2026",
                "contest_week": "1",
                "cfbd_game_id": "401858209",
                "home_public_pick_pct": "92",
                "captured_at_utc": "2026-09-04T14:01:57Z",
                "source": "user-provided ESPN screenshot",
            }
        )
    rows = slate_to_template_rows(slate)
    assert rows[0]["game_id"] == "401858209"
    assert rows[0]["is_pickem_game"] == "true"
    assert rows[0]["espn_home_pick_pct"] == "92"
    assert rows[0]["verification_status"] == "unverified"
    assert set(REQUIRED_COLUMNS) == set(rows[0])


def test_registry_isolates_fallback_and_labels_frames(tmp_path: Path) -> None:
    good = tmp_path / "good.csv"
    _write(
        good,
        [
            _row(
                game_id="10",
                verification_status="confirmed",
                verifier_1="a",
                verifier_2="b",
                source_sha256="c" * 64,
                match_status="exact_id",
            )
        ],
    )
    fallback = tmp_path / "fallback.csv"
    _write(
        fallback,
        [
            _row(
                game_id="11",
                display_order="2",
                match_status="fallback_review",
            )
        ],
    )
    registry = build_registry([good, fallback], known_game_ids={10, 11})
    assert registry.ok
    assert len(registry.rows) == 1
    assert registry.rows[0]["sampling_frame"] == SAMPLING_VERIFIED
    assert len(registry.fallback_review) == 1
    artifacts = write_registry(registry, tmp_path / "out")
    assert artifacts["registry"].exists()
    games = [{"game_id": 10}, {"game_id": 99}]
    apply_registry_labels(games, registry.rows)
    assert games[0]["sampling_frame"] == SAMPLING_VERIFIED
    assert games[1]["sampling_frame"] == SAMPLING_ALL_FBS


def test_sampling_frame_never_infers_from_prominence() -> None:
    assert sampling_frame_label(is_pickem_game=None, verification_status=None) == (
        SAMPLING_ALL_FBS
    )
    assert (
        sampling_frame_for_row({"is_pickem_game": True, "verification_status": "unverified"})
        == SAMPLING_ALL_FBS
    )


def test_unrecoverable_weeks_report() -> None:
    report = unrecoverable_weeks_report(
        research_seasons=[2024],
        recovered={(2024, 1)},
        contest_weeks_by_season={2024: [1, 2]},
    )
    assert report["unrecoverable_or_unsearched_season_weeks"] == [
        {"season": 2024, "week": 2}
    ]
