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
| `home_classification`, `away_classification` | string | NCAA classification used to define the candidate universe |
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
| `fpi_home`, `fpi_away` | float | Prior-week rating when a timestamped archive is available; otherwise null |
| `sp_home`, `sp_away` | float | Prior-week SP+ when a timestamped archive is available; otherwise null |
| `elo_home`, `elo_away` | float | Prior-week Elo rating |
| `home_entering_wins`, `home_entering_losses` | integer | Team W-L entering kickoff from prior completed games in the same season |
| `away_entering_wins`, `away_entering_losses` | integer | Same for away |
| `home_previous_result`, `away_previous_result` | integer | Prior completed game result for that team (1=win, 0=loss); null if none |
| `home_sos`, `away_sos` | float | Mean win percentage of prior opponents, using only games completed before this kickoff |
| `is_pickem_game` | boolean | Exact ESPN slate membership; null if unknown |
| `espn_home_pick_pct` | float | Public selection share captured pre-lock |
| `espn_expert_home_pct` | float | Expert consensus captured pre-lock |
| `source_snapshot` | string | Raw snapshot timestamp used for the build |

Deferred context columns (do not invent without a point-in-time source):

- Historical FPI/SP+ weekly archives (season-level CFBD pulls stay unjoined)
- Massey / Sagarin (licensing)
- Returning-QB flag (needs definition + season-specific source table)
- Rivalry flag (needs versioned mapping)
- Coach tenure / first-year coach (CFBD coaches adapter not yet ingested)

Every derived history feature has a unit test proving a future game's result
cannot alter an earlier row.
