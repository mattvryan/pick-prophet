import json
import tempfile
import unittest
from pathlib import Path

from pick_prophet.features.build import build_rows


class BuildTests(unittest.TestCase):
    def test_ratings_are_shifted_to_prior_week(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {
                "games": [{"id": 1, "season": 2025, "week": 2, "seasonType": "regular", "startDate": "2025-09-01T00:00:00Z", "homeTeam": "A", "awayTeam": "B", "homePoints": 20, "awayPoints": 10}],
                "lines": [],
                "rankings": [],
                "fpi": [{"week": 1, "team": "A", "fpi": 8}, {"week": 2, "team": "A", "fpi": 99}],
                "sp": [],
                "elo": [],
            }
            for name, rows in payloads.items():
                (root / f"{name}.json").write_text(json.dumps(rows))
            row = build_rows(root)[0]
            self.assertEqual(row["fpi_home"], 8)
            self.assertEqual(row["home_win"], 1)


if __name__ == "__main__":
    unittest.main()
