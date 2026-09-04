import csv
import json
import tempfile
import unittest
from pathlib import Path

from test_weekly import _row, _write_slate

from pick_prophet.weekly.signals import fetch_signals_snapshot


class FakeClient:
    def get(self, path, params):
        if path == "/games":
            return [
                {
                    "id": 401000001,
                    "awayTeam": "Away U",
                    "homeTeam": "Home U",
                    "startDate": "2026-09-05T19:30:00Z",
                    "neutralSite": False,
                    "venue": "Stadium",
                    "venueId": 1,
                    "awayConference": "A",
                    "homeConference": "B",
                    "awayPregameElo": 1450,
                    "homePregameElo": 1550,
                }
            ]
        if path == "/ratings/fpi":
            return [{"team": "Away U", "fpi": 1.5}, {"team": "Home U", "fpi": 8.5}]
        if path == "/ratings/sp":
            return [
                {"team": "Away U", "rating": 2.0, "ranking": 70},
                {"team": "Home U", "rating": 9.0, "ranking": 30},
            ]
        if path == "/rankings":
            return [
                {
                    "polls": [
                        {
                            "poll": "AP Top 25",
                            "ranks": [{"school": "Home U", "rank": 20}],
                        }
                    ]
                }
            ]
        raise AssertionError(path)


class WeeklySignalsTests(unittest.TestCase):
    def test_captures_structured_signals_without_a_pick(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = _write_slate(root / "slate.csv", [_row()])
            target = fetch_signals_snapshot(
                slate, client=FakeClient(), snapshot="20260904T160000Z"
            )
            with (target / "signals.csv").open() as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["venue"], "Stadium")
            self.assertEqual(row["away_pregame_elo"], "1450")
            self.assertEqual(row["home_fpi"], "8.5")
            self.assertEqual(row["home_sp_rank"], "30")
            self.assertEqual(row["home_ap_rank"], "20")
            self.assertNotIn("pick", row)
            manifest = json.loads((target / "manifest.json").read_text())
            self.assertEqual(manifest["matched_games"], 1)
            self.assertEqual(manifest["coverage"]["home_fpi"], 1.0)
            with self.assertRaises(FileExistsError):
                fetch_signals_snapshot(
                    slate, client=FakeClient(), snapshot="20260904T160000Z"
                )


if __name__ == "__main__":
    unittest.main()
