"""Unit tests for market consensus, vig removal, logits, and PIT filtering."""

from __future__ import annotations

import math
import unittest

from pick_prophet.features.market import (
    american_implied_probability,
    consensus_line,
    filter_observations_before_kickoff,
    market_logit,
    parse_provider_line,
    probability_to_american,
    provider_coverage_rows,
    remove_two_way_vig,
)


class MarketTests(unittest.TestCase):
    def test_american_odds(self):
        self.assertAlmostEqual(american_implied_probability(-150), 0.6)
        self.assertAlmostEqual(american_implied_probability(200), 1 / 3)
        self.assertIsNone(american_implied_probability(0))
        self.assertIsNone(american_implied_probability(None))

    def test_remove_vig(self):
        self.assertAlmostEqual(remove_two_way_vig(-110, -110), 0.5)
        self.assertIsNone(remove_two_way_vig(-110, None))

    def test_probability_to_american(self):
        self.assertAlmostEqual(probability_to_american(0.6), -150)
        self.assertAlmostEqual(probability_to_american(1 / 3), 200)

    def test_market_logit_bounds(self):
        self.assertAlmostEqual(market_logit(0.5), 0.0)
        self.assertAlmostEqual(market_logit(0.6), math.log(0.6 / 0.4))
        self.assertEqual(market_logit(1e-20, bound=5), -5)
        self.assertIsNone(market_logit(None))

    def test_consensus_uses_median_and_home_sign(self):
        result = consensus_line(
            [
                {
                    "spread": -3.5,
                    "overUnder": 50,
                    "homeMoneyline": -160,
                    "awayMoneyline": 140,
                },
                {
                    "spread": -4.5,
                    "overUnder": 52,
                    "homeMoneyline": -170,
                    "awayMoneyline": 150,
                },
            ]
        )
        self.assertEqual(result["spread_home"], -4.0)
        self.assertEqual(result["total"], 51.0)
        self.assertEqual(result["line_provider_count"], 2)
        self.assertIsNotNone(result["home_market_logit"])
        self.assertFalse(result["moneyline_fabricated_from_spread"])
        self.assertEqual(
            result["market_timing"],
            "cfbd_historical_closing_like_no_observation_timestamp",
        )

    def test_consensus_moneyline_does_not_cross_even_money(self):
        result = consensus_line(
            [
                {"awayMoneyline": -140, "homeMoneyline": 120},
                {"awayMoneyline": -115, "homeMoneyline": -105},
            ]
        )
        self.assertLess(result["away_moneyline"], -100)
        self.assertGreater(result["home_moneyline"], 100)
        self.assertLess(result["home_implied_prob"], 0.5)

    def test_missing_side_yields_null_probability(self):
        result = consensus_line([{"homeMoneyline": -150, "spread": -3}])
        self.assertIsNone(result["home_implied_prob"])
        self.assertIsNone(result["home_market_logit"])
        self.assertEqual(result["spread_home"], -3)

    def test_spread_only_never_fabricates_moneyline_probability(self):
        result = consensus_line([{"spread": -7.5, "overUnder": 45.0}])
        self.assertIsNone(result["home_moneyline"])
        self.assertIsNone(result["away_moneyline"])
        self.assertIsNone(result["home_implied_prob"])
        self.assertFalse(result["moneyline_fabricated_from_spread"])

    def test_open_fields_drive_movement_without_inferring_time_order(self):
        result = consensus_line(
            [
                {
                    "provider": "book",
                    "spread": -3.0,
                    "spreadOpen": -4.5,
                    "overUnder": 50,
                    "overUnderOpen": 48,
                }
            ]
        )
        self.assertEqual(result["spread_home_open"], -4.5)
        self.assertEqual(result["spread_move_home"], 1.5)
        self.assertEqual(result["total_move"], 2.0)

    def test_rejects_post_kick_observations_when_timestamped(self):
        result = consensus_line(
            [
                {
                    "provider": "early",
                    "spread": -3,
                    "homeMoneyline": -150,
                    "awayMoneyline": 130,
                    "observedAt": "2025-09-01T15:00:00Z",
                },
                {
                    "provider": "late",
                    "spread": -10,
                    "homeMoneyline": -300,
                    "awayMoneyline": 250,
                    "observedAt": "2025-09-01T20:00:00Z",
                },
            ],
            kickoff_utc="2025-09-01T18:00:00Z",
        )
        self.assertEqual(result["line_provider_count"], 1)
        self.assertEqual(result["post_kick_provider_quotes_rejected"], 1)
        self.assertEqual(result["spread_home"], -3)
        self.assertEqual(result["market_timing"], "point_in_time_filtered_by_observed_at")

    def test_filter_keeps_untimestamped_quotes(self):
        kept, rejected = filter_observations_before_kickoff(
            [
                parse_provider_line({"spread": -3, "observedAt": "2025-09-01T20:00:00Z"}),
                parse_provider_line({"spread": -4}),
            ],
            "2025-09-01T18:00:00Z",
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].spread, -4)
        self.assertEqual(len(rejected), 1)

    def test_provider_coverage_rows(self):
        rows = provider_coverage_rows(
            [
                {
                    "season": 2025,
                    "week": 1,
                    "lines": [
                        {"provider": "consensus", "spread": -3},
                        {"provider": "Caesars", "spread": -3.5},
                    ],
                }
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["provider"], "Caesars")


if __name__ == "__main__":
    unittest.main()
