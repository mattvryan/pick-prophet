import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pick_prophet.evaluation.analyze import analyze_file


class AnalysisTests(unittest.TestCase):
    def test_missing_feature_skips_fold_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for season in (2023, 2024):
                for index in range(8):
                    rows.append(
                        {
                            "season": season,
                            "home_win": index % 2,
                            "spread_home": -3 if index % 2 else 3,
                            "home_implied_prob": None,
                            "elo_home": 1500 + index,
                            "elo_away": 1500,
                            "fpi_home": None,
                            "fpi_away": None,
                            "sp_home": None,
                            "sp_away": None,
                        }
                    )
            source = root / "games.csv"
            pd.DataFrame(rows).to_csv(source, index=False)
            result = json.loads(analyze_file(source).read_text())
            self.assertEqual(result["direct_baselines"]["vig_removed_moneyline"], [])
            self.assertEqual(
                len(result["walk_forward_models"]["spread_logistic"]["folds"]), 1
            )
            self.assertEqual(result["walk_forward_models"]["fpi_logistic"]["folds"], [])
            self.assertEqual(
                result["walk_forward_models"]["fpi_logistic"]["skipped_folds"][0][
                    "reason"
                ],
                "no complete training rows",
            )


if __name__ == "__main__":
    unittest.main()
