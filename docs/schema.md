# Canonical game schema

One row represents one game. `game_id` is the CFBD identifier and is the stable
join key. Team names are display labels, never join keys when IDs are available.

| Column | Type | Meaning / timing |
|---|---|---|
| `game_id` | integer | Source game identifier |
| `season`, `week`, `season_type` | integer, integer, string | Schedule dimensions |
| `kickoff_utc` | timestamp | Scheduled start |
| `home_team`, `away_team` | string | Team names |
| `home_team_id`, `away_team_id` | integer | Stable team identifiers |
| `home_conference`, `away_conference` | string | Conference in that season |
| `neutral_site` | boolean | Neutral venue flag |
| `home_points`, `away_points` | integer | Outcome; null pre-game |
| `home_win` | integer | Binary target; null pre-game/tie |
| `spread_home` | float | Consensus closing spread from home perspective; negative means home favored |
| `total` | float | Consensus closing total |
| `home_moneyline`, `away_moneyline` | float | Consensus closing American odds |
| `line_provider_count` | integer | Number of books contributing |
| `home_implied_prob` | float | Vig-removed two-way moneyline probability |
| `ap_home_rank`, `ap_away_rank` | integer | Latest pre-game AP ranks; unranked is null |
| `coaches_home_rank`, `coaches_away_rank` | integer | Latest pre-game Coaches ranks |
| `cfp_home_rank`, `cfp_away_rank` | integer | Latest pre-game CFP ranks |
| `fpi_home`, `fpi_away` | float | Prior-week rating |
| `sp_home`, `sp_away` | float | Prior-week SP+ rating |
| `elo_home`, `elo_away` | float | Prior-week Elo rating |
| `is_pickem_game` | boolean | Exact ESPN slate membership; null if unknown |
| `espn_home_pick_pct` | float | Public selection share captured pre-lock |
| `espn_expert_home_pct` | float | Expert consensus captured pre-lock |
| `source_snapshot` | string | Raw snapshot timestamp used for the build |

Planned context columns (`entering_wins`, `entering_losses`, previous result,
SOS, coach tenure, first-year coach, returning QB, rivalry) remain out of the
canonical table until a point-in-time source and tests exist. This is preferable
to creating plausible-looking hindsight features.
