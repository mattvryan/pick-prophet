from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from pick_prophet.weekly.tiebreaker import recommend_tiebreaker


class TiebreakerTests(unittest.TestCase):
    def test_half_point_rounds_up_and_is_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = root / "slate.csv"
            with slate.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "display_order",
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
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "display_order": 1,
                        "cfbd_game_id": "123",
                        "away_team": "Clemson",
                        "home_team": "LSU",
                        "neutral_site": "false",
                        "away_moneyline": "+300",
                        "home_moneyline": "-400",
                        "away_public_pick_pct": 10,
                        "home_public_pick_pct": 90,
                        "lock_at_utc": "2026-09-05T23:30:00Z",
                        "captured_at_utc": "2026-09-04T14:00:00Z",
                    }
                )
            market = root / "market.csv"
            with market.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "cfbd_game_id",
                        "away_team",
                        "home_team",
                        "total",
                        "snapshot_at_utc",
                        "status",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "cfbd_game_id": "123",
                        "away_team": "Clemson",
                        "home_team": "LSU",
                        "total": "50.5",
                        "snapshot_at_utc": "2026-09-04T14:46:39Z",
                        "status": "ok",
                    }
                )

            artifacts = recommend_tiebreaker(
                slate,
                market,
                game_id="123",
                as_of="2026-09-04T16:00:00Z",
                output_dir=root / "output",
                generated_at="2026-09-04T16:01:00Z",
            )
            payload = json.loads(artifacts["json"].read_text())
            self.assertEqual(payload["recommended_integer_total"], 51)
            self.assertEqual(payload["consensus_market_total"], 50.5)
            self.assertIn("51 points", artifacts["card"].read_text())

    def test_rejects_team_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slate = root / "slate.csv"
            slate.write_text(
                "display_order,cfbd_game_id,espn_game_id,away_team,home_team,neutral_site,away_moneyline,home_moneyline,away_public_pick_pct,home_public_pick_pct,lock_at_utc,captured_at_utc\n"
                "1,123,,Clemson,LSU,false,+300,-400,10,90,2026-09-05T23:30:00Z,2026-09-04T14:00:00Z\n"
            )
            market = root / "market.csv"
            market.write_text(
                "cfbd_game_id,away_team,home_team,total,status\n"
                "123,Clemson,Other,50.5,ok\n"
            )
            with self.assertRaisesRegex(ValueError, "team mismatch"):
                recommend_tiebreaker(
                    slate,
                    market,
                    game_id="123",
                    as_of="2026-09-04T16:00:00Z",
                    output_dir=root / "output",
                )
