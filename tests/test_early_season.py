import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pick_prophet.evaluation.early_season import analyze_early_season


class EarlySeasonTests(unittest.TestCase):
    def test_models_use_identical_rows_and_write_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            game_id = 1
            for season in (2022, 2023, 2024):
                for week in range(1, 6):
                    for home_win in (0, 1, 0, 1):
                        rows.append(
                            {
                                "game_id": game_id,
                                "season": season,
                                "week": week,
                                "home_win": home_win,
                                "spread_home": -3 if home_win else 3,
                                "elo_home": 1510 if home_win else 1490,
                                "elo_away": 1500,
                            }
                        )
                        game_id += 1
            source = root / "games.csv"
            pd.DataFrame(rows).to_csv(source, index=False)
            artifacts = analyze_early_season(source, root / "out")
            summary = json.loads(artifacts["summary"].read_text())
            week_1 = summary["slices"]["week_1"]
            self.assertEqual(week_1["folds"], 2)
            self.assertEqual(week_1["test_n"], 8)
            predictions = pd.read_csv(artifacts["predictions"])
            counts = predictions.groupby(["slice", "model"]).size()
            self.assertEqual(
                counts["week_1", "spread"], counts["week_1", "spread_plus_elo"]
            )


if __name__ == "__main__":
    unittest.main()
