"""Synthetic-slate tests for weekly validate-slate and recommend."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from pick_prophet.weekly.recommend import OUTPUT_SCHEMA_VERSION, recommend
from pick_prophet.weekly.validate import ValidationResult, validate_slate

HEADERS = [
    "display_order",
    "season",
    "contest_week",
    "cfbd_game_id",
    "espn_game_id",
    "away_team",
    "home_team",
    "neutral_site",
    "away_moneyline",
    "home_moneyline",
    "away_public_pick_pct",
    "home_public_pick_pct",
    "lock_at_utc",
    "captured_at_utc",
]


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "display_order": "1",
        "season": "2026",
        "contest_week": "1",
        "cfbd_game_id": "401000001",
        "espn_game_id": "",
        "away_team": "Away U",
        "home_team": "Home U",
        "neutral_site": "false",
        "away_moneyline": "+150",
        "home_moneyline": "-170",
        "away_public_pick_pct": "20",
        "home_public_pick_pct": "80",
        "lock_at_utc": "2026-09-05T19:30:00Z",
        "captured_at_utc": "2026-09-04T14:00:00Z",
    }
    base.update(overrides)
    return base


def _write_slate(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in HEADERS})
    return path


class ValidateSlateTests(unittest.TestCase):
    def test_valid_standard_slate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [
                    _row(),
                    _row(
                        display_order="2",
                        cfbd_game_id="401000002",
                        away_team="B",
                        home_team="C",
                        away_moneyline="-148",
                        home_moneyline="+124",
                        away_public_pick_pct="55",
                        home_public_pick_pct="45",
                    ),
                ],
            )
            result = validate_slate(slate)
            self.assertIsInstance(result, ValidationResult)
            self.assertEqual(result.errors, [])
            self.assertEqual(len(result.rows), 2)
            self.assertTrue(
                any("espn_game_id" in warning.lower() for warning in result.warnings)
            )

    def test_duplicate_display_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [_row(), _row(cfbd_game_id="401000002", away_team="X", home_team="Y")],
            )
            result = validate_slate(slate)
            self.assertTrue(any("display_order" in error for error in result.errors))

    def test_duplicate_cfbd_game_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [
                    _row(),
                    _row(display_order="2", away_team="X", home_team="Y"),
                ],
            )
            result = validate_slate(slate)
            self.assertTrue(any("cfbd_game_id" in error for error in result.errors))

    def test_malformed_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [_row(lock_at_utc="not-a-timestamp")],
            )
            result = validate_slate(slate)
            self.assertTrue(any("lock_at_utc" in error for error in result.errors))

    def test_capture_after_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [
                    _row(
                        captured_at_utc="2026-09-05T20:00:00Z",
                        lock_at_utc="2026-09-05T19:30:00Z",
                    )
                ],
            )
            result = validate_slate(slate)
            self.assertTrue(
                any("captured_at_utc" in error and "lock" in error for error in result.errors)
            )

    def test_as_of_after_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(Path(directory) / "slate.csv", [_row()])
            result = validate_slate(slate, as_of="2026-09-05T20:00:00Z")
            self.assertTrue(any("as-of" in error.lower() or "as_of" in error for error in result.errors))

    def test_invalid_moneyline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [_row(away_moneyline="+50", home_moneyline="-60")],
            )
            result = validate_slate(slate)
            self.assertTrue(any("moneyline" in error.lower() for error in result.errors))

    def test_two_negative_moneylines_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [_row(away_moneyline="-115", home_moneyline="-105")],
            )
            result = validate_slate(slate)
            moneyline_errors = [e for e in result.errors if "moneyline" in e.lower()]
            self.assertEqual(moneyline_errors, [])

    def test_public_percentages_must_total_100(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [_row(away_public_pick_pct="10", home_public_pick_pct="80")],
            )
            result = validate_slate(slate)
            self.assertTrue(any("public" in error.lower() for error in result.errors))

    def test_missing_moneyline_warns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [_row(away_moneyline="", home_moneyline="")],
            )
            result = validate_slate(slate)
            self.assertEqual(result.errors, [])
            self.assertTrue(any("moneyline" in warning.lower() for warning in result.warnings))

    def test_same_team_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [_row(away_team="Duke", home_team="Duke")],
            )
            result = validate_slate(slate)
            self.assertTrue(any("same" in error.lower() or "equal" in error.lower() for error in result.errors))

    def test_neutral_site_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            slate = _write_slate(
                Path(directory) / "slate.csv",
                [_row(neutral_site="maybe")],
            )
            result = validate_slate(slate)
            self.assertTrue(any("neutral_site" in error for error in result.errors))


class RecommendTests(unittest.TestCase):
    def test_vig_removal_and_favorite_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = _write_slate(
                root / "slate.csv",
                [_row(away_moneyline="+150", home_moneyline="-170")],
            )
            output = root / "output" / "run1"
            artifacts = recommend(slate, as_of="2026-09-05T12:00:00Z", output_dir=output)
            with artifacts["recommendations"].open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["baseline_pick"], "Home U")
            self.assertGreater(float(row["home_market_probability"]), 0.5)
            self.assertAlmostEqual(
                float(row["away_market_probability"]) + float(row["home_market_probability"]),
                1.0,
                places=9,
            )
            self.assertEqual(row["upset_candidate"], "false")
            self.assertEqual(row["recommendation_status"], "ok")
            self.assertNotIn("confidence_rank", row)
            card = artifacts["card"].read_text(encoding="utf-8")
            self.assertIn("Market baseline — not the final submitted card", card)
            self.assertIn("no confidence points", card.lower())
            self.assertIn("Home U", card)
            manifest = json.loads(artifacts["run_manifest"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["output_schema_version"], OUTPUT_SCHEMA_VERSION)
            self.assertEqual(manifest["contest_mode"], "standard")
            self.assertEqual(manifest["row_count"], 1)
            self.assertEqual(manifest["valid_recommendation_count"], 1)
            self.assertIn("generation_timestamp", manifest)
            self.assertIn("output_hashes", manifest)

    def test_missing_moneyline_insufficient_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = _write_slate(
                root / "slate.csv",
                [_row(away_moneyline="", home_moneyline="")],
            )
            output = root / "output" / "run-missing"
            artifacts = recommend(slate, as_of="2026-09-05T12:00:00Z", output_dir=output)
            with artifacts["recommendations"].open(encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["recommendation_status"], "insufficient_data")
            self.assertEqual(row["baseline_pick"], "")
            self.assertEqual(row["away_market_probability"], "")
            self.assertEqual(row["home_market_probability"], "")

    def test_preserves_espn_display_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = _write_slate(
                root / "slate.csv",
                [
                    _row(
                        display_order="2",
                        cfbd_game_id="401000002",
                        away_team="Second",
                        home_team="Home2",
                        away_moneyline="+200",
                        home_moneyline="-250",
                    ),
                    _row(
                        display_order="1",
                        cfbd_game_id="401000001",
                        away_team="First",
                        home_team="Home1",
                        away_moneyline="+130",
                        home_moneyline="-150",
                    ),
                ],
            )
            output = root / "output" / "order"
            artifacts = recommend(slate, as_of="2026-09-05T12:00:00Z", output_dir=output)
            with artifacts["recommendations"].open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["display_order"] for row in rows], ["1", "2"])
            self.assertEqual([row["away_team"] for row in rows], ["First", "Second"])
            card = artifacts["card"].read_text(encoding="utf-8")
            self.assertLess(card.index("First"), card.index("Second"))

    def test_public_disagreement_not_used_for_pick(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Market loves home; public loves away.
            slate = _write_slate(
                root / "slate.csv",
                [
                    _row(
                        away_moneyline="+200",
                        home_moneyline="-250",
                        away_public_pick_pct="90",
                        home_public_pick_pct="10",
                    )
                ],
            )
            output = root / "output" / "public"
            artifacts = recommend(slate, as_of="2026-09-05T12:00:00Z", output_dir=output)
            with artifacts["recommendations"].open(encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["baseline_pick"], "Home U")
            expected = float(row["home_market_probability"]) - 0.10
            self.assertAlmostEqual(float(row["public_disagreement"]), expected, places=9)

    def test_deterministic_recommendations_and_card(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = _write_slate(root / "slate.csv", [_row()])
            first = recommend(
                slate, as_of="2026-09-05T12:00:00Z", output_dir=root / "output" / "a"
            )
            second = recommend(
                slate, as_of="2026-09-05T12:00:00Z", output_dir=root / "output" / "b"
            )
            self.assertEqual(
                first["recommendations"].read_bytes(),
                second["recommendations"].read_bytes(),
            )
            self.assertEqual(first["card"].read_bytes(), second["card"].read_bytes())
            manifest_a = json.loads(first["run_manifest"].read_text(encoding="utf-8"))
            manifest_b = json.loads(second["run_manifest"].read_text(encoding="utf-8"))
            self.assertNotEqual(
                manifest_a["generation_timestamp"], manifest_b["generation_timestamp"]
            )

    def test_refuses_overwrite_finalized_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = _write_slate(root / "slate.csv", [_row()])
            output = root / "output" / "final"
            recommend(slate, as_of="2026-09-05T12:00:00Z", output_dir=output)
            (output / "FINALIZED").write_text("locked\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                recommend(slate, as_of="2026-09-05T12:00:00Z", output_dir=output)

    def test_recommend_rejects_as_of_after_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = _write_slate(root / "slate.csv", [_row()])
            with self.assertRaises(ValueError):
                recommend(
                    slate,
                    as_of="2026-09-05T20:00:00Z",
                    output_dir=root / "output" / "late",
                )


if __name__ == "__main__":
    unittest.main()
