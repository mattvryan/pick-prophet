import unittest

from pick_prophet.features.market import (
    american_implied_probability,
    consensus_line,
    remove_two_way_vig,
)


class MarketTests(unittest.TestCase):
    def test_american_odds(self):
        self.assertAlmostEqual(american_implied_probability(-150), 0.6)
        self.assertAlmostEqual(american_implied_probability(200), 1 / 3)

    def test_remove_vig(self):
        self.assertAlmostEqual(remove_two_way_vig(-110, -110), 0.5)

    def test_consensus_uses_median_and_home_sign(self):
        result = consensus_line([
            {"spread": -3.5, "overUnder": 50, "homeMoneyline": -160, "awayMoneyline": 140},
            {"spread": -4.5, "overUnder": 52, "homeMoneyline": -170, "awayMoneyline": 150},
        ])
        self.assertEqual(result["spread_home"], -4.0)
        self.assertEqual(result["total"], 51.0)
        self.assertEqual(result["line_provider_count"], 2)


if __name__ == "__main__":
    unittest.main()
