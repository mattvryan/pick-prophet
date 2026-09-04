# M07 modeling matrix schema

**Version:** `matrix_schema_version = "1.0.0"`
**Code:** `src/pick_prophet/features/matrix_schema.py`
**Design:** `docs/superpowers/specs/2026-09-04-m07-feature-matrix-design.md`

One row per eligible FBS game. Header order is the ordered union of five
pairwise-disjoint role lists. M08 may use only `BASELINE_INPUT_COLUMNS` as the
market offset and `MODEL_FEATURE_COLUMNS` as adjustment predictors.

## Serialization

| Kind | CSV representation |
|---|---|
| boolean | `true` / `false` |
| null | empty field |
| timestamp | UTC ISO-8601 |
| Pick’em percentages | percentage points in `[0, 100]` |
| JSON artifacts | sorted keys, compact separators |

Rows sort by `(kickoff_utc, game_id)`. Deferred Elo/FPI/SP+ are **not** columns;
they appear only in `matrix_manifest.json` → `ratings_inventory`.

## Rebuild

```bash
pick-prophet matrix --input-dir data/processed --seasons 2017-2025 --output-dir data/processed/matrix
```

Outputs: `games_matrix_v1.csv`, `matrix_missingness.csv`, `matrix_exclusions.csv`,
`matrix_manifest.json` (deterministic), `matrix_run.json` (volatile timestamp).

## Column catalog

| Column | Role | Type | Null | Units / domain | Timing |
|---|---|---|---|---|---|
| `game_id` | IDENTIFIER | int | no | CFBD id | schedule |
| `season` | IDENTIFIER | int | no | YYYY | schedule |
| `week` | IDENTIFIER | int | no | contest week | schedule |
| `season_type` | IDENTIFIER | string | yes | e.g. regular/postseason | schedule |
| `kickoff_utc` | IDENTIFIER | timestamp | no | UTC | scheduled start |
| `home_team_id` | IDENTIFIER | int | yes* | CFBD team id | schedule |
| `away_team_id` | IDENTIFIER | int | yes* | CFBD team id | schedule |
| `home_team` | IDENTIFIER | string | yes* | display only | schedule |
| `away_team` | IDENTIFIER | string | yes* | display only | schedule |
| `home_win` | TARGET | int | yes | `{0,1}`; null pregame/tie | postgame |
| `home_implied_prob` | BASELINE | float | yes | vig-free `[0,1]` | M04 closing-like / PIT |
| `home_market_logit` | BASELINE | float | yes | bounded logit | derived from prob |
| `home_conference` | MODEL | string | yes | season conference | pregame |
| `away_conference` | MODEL | string | yes | season conference | pregame |
| `home_classification` | MODEL | string | yes | e.g. fbs | schedule |
| `away_classification` | MODEL | string | yes | e.g. fbs | schedule |
| `neutral_site` | MODEL | bool | yes | true/false | schedule |
| `home_field_advantage` | MODEL | int | yes | `1` if not neutral else `0` | derived |
| `is_week_1` | MODEL | bool | no | `week==1` | derived |
| `is_weeks_1_3` | MODEL | bool | no | `1<=week<=3` | derived |
| `spread_home` | MODEL | float | yes | home perspective | M04 |
| `total` | MODEL | float | yes | points | M04 |
| `home_moneyline` | MODEL | float | yes | American | M04 |
| `away_moneyline` | MODEL | float | yes | American | M04 |
| `line_provider_count` | MODEL | int | yes | books after PIT filter | M04 |
| `spread_home_open` | MODEL | float | yes | labeled open only | M04 |
| `total_open` | MODEL | float | yes | labeled open only | M04 |
| `spread_move_home` | MODEL | float | yes | close−open if both labeled | M04 |
| `total_move` | MODEL | float | yes | close−open if both labeled | M04 |
| `home_entering_wins` | MODEL | int | no† | prior completed W | chronological |
| `home_entering_losses` | MODEL | int | no† | prior completed L | chronological |
| `away_entering_wins` | MODEL | int | no† | prior completed W | chronological |
| `away_entering_losses` | MODEL | int | no† | prior completed L | chronological |
| `home_previous_result` | MODEL | int | yes | `{0,1}` prior result | chronological |
| `away_previous_result` | MODEL | int | yes | `{0,1}` prior result | chronological |
| `home_sos` | MODEL | float | yes | mean opp win% | chronological |
| `away_sos` | MODEL | float | yes | mean opp win% | chronological |
| `home_days_rest` | MODEL | int | yes | floor days since prior completed kickoff | chronological proxy |
| `away_days_rest` | MODEL | int | yes | floor days since prior completed kickoff | chronological proxy |
| `source_snapshot` | AUDIT | string | yes | raw snapshot id | build |
| `market_timing` | AUDIT | string | yes | M04 timing label | market |
| `post_kick_provider_quotes_rejected` | AUDIT | int | yes | count | market |
| `moneyline_fabricated_from_spread` | AUDIT | bool | yes | always false when set | market |
| `sampling_frame` | AUDIT | string | no | `all_fbs` / `verified_espn_pickem` | Pick’em |
| `verification_status` | AUDIT | string | yes | import status | Pick’em |
| `match_status` | AUDIT | string | yes | join status | Pick’em |
| `is_pickem_game` | AUDIT | bool | yes | slate membership | Pick’em |
| `espn_home_pick_pct` | AUDIT | float | yes | `[0,100]` public | Pick’em eval only |
| `espn_expert_home_pct` | AUDIT | float | yes | `[0,100]` expert | Pick’em eval only |

\* Structural exclusion requires each side to have `team_id` **or** non-empty name.
† Entering W-L default to `0` with no prior games (not null).

## History semantics

History/rest are **recomputed** in M07 (`attach_matrix_history`); processed
history columns are not trusted. Ordering is `(kickoff_utc, game_id)`. Only
prior completed same-season games update records. Rest uses prior kickoff as
completion proxy; non-positive intervals raise. Regular-season games may feed
later postseason rows; chrono order prevents reverse leakage.

## Ratings inventory (manifest only)

Elo, FPI, and SP+ remain `deferred` with refs to `docs/ratings_feasibility.md`.
A future rating-family PR bumps `matrix_schema_version` and extends role lists.
