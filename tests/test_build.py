import json
import tempfile
import unittest
from pathlib import Path

from pick_prophet.features.build import build_rows


class BuildTests(unittest.TestCase):
    def test_weekly_elo_is_shifted_to_prior_week(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {
                "games": [
                    {
                        "id": 1,
                        "season": 2025,
                        "week": 2,
                        "seasonType": "regular",
                        "startDate": "2025-09-01T00:00:00Z",
                        "homeTeam": "A",
                        "awayTeam": "B",
                        "homeClassification": "fbs",
                        "awayClassification": "fbs",
                        "homePoints": 20,
                        "awayPoints": 10,
                    }
                ],
                "lines": [],
                "rankings": [],
                "fpi": [],
                "sp": [],
                "elo": [
                    {"week": 1, "team": "A", "elo": 1508},
                    {"week": 2, "team": "A", "elo": 1999},
                ],
            }
            for name, rows in payloads.items():
                (root / f"{name}.json").write_text(json.dumps(rows))
            result = build_rows(root)
            row = result.rows[0]
            self.assertEqual(row["elo_home"], 1508)
            self.assertIsNone(row["fpi_home"])
            self.assertEqual(row["home_win"], 1)
            elo_joins = [a for a in result.name_join_audit if a["feature"] == "elo"]
            self.assertTrue(elo_joins)
            self.assertTrue(any(a["resolved"] for a in elo_joins))
            self.assertTrue(all(a["join_key_type"] == "name" for a in elo_joins))

    def test_build_exposes_market_logit_and_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {
                "games": [
                    {
                        "id": 1,
                        "season": 2025,
                        "week": 2,
                        "seasonType": "regular",
                        "startDate": "2025-09-01T18:00:00Z",
                        "homeTeam": "A",
                        "awayTeam": "B",
                        "homeClassification": "fbs",
                        "awayClassification": "fbs",
                        "homePoints": 20,
                        "awayPoints": 10,
                    }
                ],
                "lines": [
                    {
                        "id": 1,
                        "lines": [
                            {
                                "provider": "book",
                                "spread": -3.5,
                                "spreadOpen": -2.5,
                                "overUnder": 50,
                                "homeMoneyline": -150,
                                "awayMoneyline": 130,
                            }
                        ],
                    }
                ],
                "rankings": [],
                "fpi": [],
                "sp": [],
                "elo": [],
            }
            for name, rows in payloads.items():
                (root / f"{name}.json").write_text(json.dumps(rows))
            row = build_rows(root).rows[0]
            # Vig-removed two-way probability, not the raw -150 American imply.
            self.assertAlmostEqual(row["home_implied_prob"], 0.5798319327731093, places=8)
            self.assertIsNotNone(row["home_market_logit"])
            self.assertEqual(row["spread_move_home"], -1.0)
            self.assertFalse(row["moneyline_fabricated_from_spread"])
            self.assertEqual(
                row["market_timing"],
                "cfbd_historical_closing_like_no_observation_timestamp",
            )


if __name__ == "__main__":
    unittest.main()
