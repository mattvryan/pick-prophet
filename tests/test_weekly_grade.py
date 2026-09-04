"""Synthetic tests for weekly result capture and grading."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from pick_prophet.weekly.grade import SCHEMA_VERSION, grade_week
from pick_prophet.weekly.results import fetch_results

RESULT_HEADERS = [
    "display_order",
    "cfbd_game_id",
    "away_team",
    "home_team",
    "away_points",
    "home_points",
    "winner",
    "total_points",
]


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})
    return path


def _week_fixture(root: Path) -> Path:
    week = root / "2026-W01"
    week.mkdir()
    _write_csv(
        week / "final_picks.csv",
        [
            "display_order",
            "away_team",
            "home_team",
            "pick",
            "market_win_probability",
            "manual_override",
            "review_note",
        ],
        [
            {
                "display_order": "1",
                "away_team": "Away U",
                "home_team": "Home U",
                "pick": "Home U",
                "market_win_probability": "0.70",
                "manual_override": "false",
                "review_note": "baseline",
            },
            {
                "display_order": "2",
                "away_team": "Dog",
                "home_team": "Fav",
                "pick": "Dog",
                "market_win_probability": "0.40",
                "manual_override": "true",
                "review_note": "override",
            },
        ],
    )
    (week / "submission.json").write_text(
        json.dumps(
            {
                "schema_version": "weekly_submission.v1",
                "submitted_at_utc": "2026-09-04T18:30:00Z",
                "tiebreaker_total": 51,
                "picks": [
                    {
                        "display_order": 1,
                        "away_team": "Away U",
                        "home_team": "Home U",
                        "pick": "Home U",
                        "manual_override": False,
                        "market_win_probability": "0.70",
                    },
                    {
                        "display_order": 2,
                        "away_team": "Dog",
                        "home_team": "Fav",
                        "pick": "Dog",
                        "manual_override": True,
                        "market_win_probability": "0.40",
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rec_dir = week / "recommendations-current"
    rec_dir.mkdir()
    _write_csv(
        rec_dir / "recommendations.csv",
        [
            "display_order",
            "cfbd_game_id",
            "away_team",
            "home_team",
            "baseline_pick",
            "baseline_pick_probability",
            "recommendation_status",
        ],
        [
            {
                "display_order": "1",
                "cfbd_game_id": "1",
                "away_team": "Away U",
                "home_team": "Home U",
                "baseline_pick": "Home U",
                "baseline_pick_probability": "0.70",
                "recommendation_status": "ok",
            },
            {
                "display_order": "2",
                "cfbd_game_id": "2",
                "away_team": "Dog",
                "home_team": "Fav",
                "baseline_pick": "Fav",
                "baseline_pick_probability": "0.60",
                "recommendation_status": "ok",
            },
        ],
    )
    tb = week / "tiebreaker"
    tb.mkdir()
    (tb / "tiebreaker.json").write_text(
        json.dumps(
            {
                "cfbd_game_id": "1",
                "recommended_integer_total": 51,
                "away_team": "Away U",
                "home_team": "Home U",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_csv(
        week / "results.csv",
        RESULT_HEADERS,
        [
            {
                "display_order": "1",
                "cfbd_game_id": "1",
                "away_team": "Away U",
                "home_team": "Home U",
                "away_points": "17",
                "home_points": "24",
                "winner": "Home U",
                "total_points": "41",
            },
            {
                "display_order": "2",
                "cfbd_game_id": "2",
                "away_team": "Dog",
                "home_team": "Fav",
                "away_points": "21",
                "home_points": "14",
                "winner": "Dog",
                "total_points": "35",
            },
        ],
    )
    return week


class GradeWeekTests(unittest.TestCase):
    def test_grades_submitted_picks_against_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            week = _week_fixture(Path(directory))
            artifacts = grade_week(
                week_dir=week,
                results_path=week / "results.csv",
                graded_at="2026-09-08T12:00:00Z",
            )
            payload = json.loads(artifacts["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
            self.assertEqual(payload["games"], 2)
            self.assertEqual(payload["correct"], 2)
            self.assertEqual(payload["accuracy"], 1.0)
            self.assertEqual(payload["baseline_correct"], 1)
            self.assertEqual(payload["baseline_accuracy"], 0.5)
            self.assertEqual(payload["override_games"], 1)
            self.assertEqual(payload["override_correct"], 1)
            self.assertEqual(payload["override_delta_vs_baseline"], 1)
            self.assertEqual(payload["tiebreaker"]["submitted_total"], 51)
            self.assertEqual(payload["tiebreaker"]["actual_total"], 41)
            self.assertEqual(payload["tiebreaker"]["absolute_error"], 10)
            self.assertIn("brier", payload["probability_metrics"])
            self.assertIn("log_loss", payload["probability_metrics"])
            self.assertTrue(artifacts["markdown"].exists())
            self.assertIn("2/2", artifacts["markdown"].read_text(encoding="utf-8"))

    def test_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            week = _week_fixture(Path(directory))
            grade_week(
                week_dir=week,
                results_path=week / "results.csv",
                graded_at="2026-09-08T12:00:00Z",
            )
            with self.assertRaises(FileExistsError):
                grade_week(
                    week_dir=week,
                    results_path=week / "results.csv",
                    graded_at="2026-09-08T13:00:00Z",
                )


class FetchResultsTests(unittest.TestCase):
    def test_writes_results_when_all_games_complete(self) -> None:
        class FakeClient:
            def get(self, path, params):
                assert path == "/games"
                return [
                    {
                        "id": 1,
                        "awayTeam": "Away U",
                        "homeTeam": "Home U",
                        "awayPoints": 10,
                        "homePoints": 20,
                        "completed": True,
                    },
                    {
                        "id": 2,
                        "awayTeam": "Dog",
                        "homeTeam": "Fav",
                        "awayPoints": 21,
                        "homePoints": 14,
                        "completed": True,
                    },
                ]

        with tempfile.TemporaryDirectory() as directory:
            week = Path(directory)
            _write_csv(
                week / "slate.csv",
                [
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
                ],
                [
                    {
                        "display_order": "1",
                        "season": "2026",
                        "contest_week": "1",
                        "cfbd_game_id": "1",
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
                    },
                    {
                        "display_order": "2",
                        "season": "2026",
                        "contest_week": "1",
                        "cfbd_game_id": "2",
                        "espn_game_id": "",
                        "away_team": "Dog",
                        "home_team": "Fav",
                        "neutral_site": "false",
                        "away_moneyline": "+150",
                        "home_moneyline": "-170",
                        "away_public_pick_pct": "40",
                        "home_public_pick_pct": "60",
                        "lock_at_utc": "2026-09-05T19:30:00Z",
                        "captured_at_utc": "2026-09-04T14:00:00Z",
                    },
                ],
            )
            path = fetch_results(week_dir=week, client=FakeClient(), snapshot="20260908T120000Z")
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["winner"], "Home U")
            self.assertEqual(rows[1]["total_points"], "35")

    def test_fails_when_games_incomplete(self) -> None:
        class FakeClient:
            def get(self, path, params):
                return [
                    {
                        "id": 1,
                        "awayTeam": "Away U",
                        "homeTeam": "Home U",
                        "awayPoints": None,
                        "homePoints": None,
                        "completed": False,
                    }
                ]

        with tempfile.TemporaryDirectory() as directory:
            week = Path(directory)
            _write_csv(
                week / "slate.csv",
                [
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
                ],
                [
                    {
                        "display_order": "1",
                        "season": "2026",
                        "contest_week": "1",
                        "cfbd_game_id": "1",
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
                ],
            )
            with self.assertRaises(ValueError):
                fetch_results(week_dir=week, client=FakeClient())


if __name__ == "__main__":
    unittest.main()
