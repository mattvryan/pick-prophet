"""Tests for immutable ESPN submission confirmation records."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from pick_prophet.weekly.submission import SCHEMA_VERSION, record_submission

FINAL_HEADERS = [
    "display_order",
    "away_team",
    "home_team",
    "pick",
    "market_win_probability",
    "manual_override",
    "review_note",
]


def _write_final_picks(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FINAL_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FINAL_HEADERS})
    return path


def _sample_rows() -> list[dict[str, object]]:
    return [
        {
            "display_order": "1",
            "away_team": "Away U",
            "home_team": "Home U",
            "pick": "Home U",
            "market_win_probability": "0.61",
            "manual_override": "false",
            "review_note": "baseline",
        },
        {
            "display_order": "2",
            "away_team": "Second",
            "home_team": "Host",
            "pick": "Second",
            "market_win_probability": "0.55",
            "manual_override": "true",
            "review_note": "injury news",
        },
    ]


class SubmissionRecordTests(unittest.TestCase):
    def test_records_immutable_submission_from_final_picks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            week = Path(directory)
            picks = _write_final_picks(week / "final_picks.csv", _sample_rows())
            (week / "final_card.md").write_text("# final\n", encoding="utf-8")
            confirmation = week / "espn-confirm.png"
            confirmation.write_bytes(b"fake-png-bytes")

            artifact = record_submission(
                week_dir=week,
                submitted_at="2026-09-04T18:30:00Z",
                tiebreaker_total=51,
                operator="tester",
                confirmation_file=confirmation,
                notes="entered in ESPN UI",
                recorded_at="2026-09-04T18:31:00Z",
            )
            self.assertEqual(artifact.name, "submission.json")
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
            self.assertEqual(payload["submitted_at_utc"], "2026-09-04T18:30:00Z")
            self.assertEqual(payload["recorded_at_utc"], "2026-09-04T18:31:00Z")
            self.assertEqual(payload["operator"], "tester")
            self.assertEqual(payload["tiebreaker_total"], 51)
            self.assertTrue(payload["matches_final_picks"])
            self.assertEqual(len(payload["picks"]), 2)
            self.assertEqual(payload["picks"][0]["pick"], "Home U")
            self.assertEqual(payload["picks"][1]["manual_override"], True)
            self.assertEqual(payload["final_picks_path"], str(picks))
            self.assertEqual(len(payload["final_picks_sha256"]), 64)
            self.assertEqual(len(payload["final_card_sha256"]), 64)
            self.assertEqual(len(payload["confirmation_sha256"]), 64)
            self.assertEqual(payload["confirmation_path"], str(confirmation))
            self.assertEqual(payload["notes"], "entered in ESPN UI")

    def test_detects_mismatch_against_final_picks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            week = Path(directory)
            _write_final_picks(week / "final_picks.csv", _sample_rows())
            submitted = _write_final_picks(
                week / "submitted_picks.csv",
                [
                    _sample_rows()[0],
                    {
                        **_sample_rows()[1],
                        "pick": "Host",
                        "manual_override": "false",
                        "review_note": "entered differently",
                    },
                ],
            )
            artifact = record_submission(
                week_dir=week,
                submitted_at="2026-09-04T18:30:00Z",
                tiebreaker_total=51,
                submitted_picks=submitted,
                recorded_at="2026-09-04T18:31:00Z",
            )
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertFalse(payload["matches_final_picks"])
            self.assertEqual(payload["picks"][1]["pick"], "Host")
            self.assertEqual(len(payload["mismatches"]), 1)
            self.assertEqual(payload["mismatches"][0]["display_order"], 2)

    def test_rejects_pick_that_is_not_a_team(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            week = Path(directory)
            rows = _sample_rows()
            rows[0]["pick"] = "Nobody"
            _write_final_picks(week / "final_picks.csv", rows)
            with self.assertRaises(ValueError):
                record_submission(
                    week_dir=week,
                    submitted_at="2026-09-04T18:30:00Z",
                    tiebreaker_total=51,
                    recorded_at="2026-09-04T18:31:00Z",
                )

    def test_refuses_overwrite_existing_submission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            week = Path(directory)
            _write_final_picks(week / "final_picks.csv", _sample_rows())
            record_submission(
                week_dir=week,
                submitted_at="2026-09-04T18:30:00Z",
                tiebreaker_total=51,
                recorded_at="2026-09-04T18:31:00Z",
            )
            with self.assertRaises(FileExistsError):
                record_submission(
                    week_dir=week,
                    submitted_at="2026-09-04T19:00:00Z",
                    tiebreaker_total=51,
                    recorded_at="2026-09-04T19:01:00Z",
                )

    def test_allows_versioned_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            week = Path(directory)
            _write_final_picks(week / "final_picks.csv", _sample_rows())
            record_submission(
                week_dir=week,
                submitted_at="2026-09-04T18:30:00Z",
                tiebreaker_total=51,
                recorded_at="2026-09-04T18:31:00Z",
            )
            second = record_submission(
                week_dir=week,
                submitted_at="2026-09-04T19:00:00Z",
                tiebreaker_total=52,
                output_path=week / "submission-20260904T190000Z.json",
                recorded_at="2026-09-04T19:01:00Z",
            )
            self.assertTrue(second.exists())
            payload = json.loads(second.read_text(encoding="utf-8"))
            self.assertEqual(payload["tiebreaker_total"], 52)


if __name__ == "__main__":
    unittest.main()
