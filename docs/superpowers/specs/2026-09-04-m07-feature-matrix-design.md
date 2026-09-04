# M07 leakage-safe modeling feature matrix design

Date: 2026-09-04
Status: approved for implementation planning
Roadmap: `docs/modeling_implementation_roadmap.md` § M07
Branch: `modeling/m07-feature-matrix`

## Problem

M08+ needs a single versioned, leakage-safe feature table. Processed season
CSVs currently mix market/history fields with deferred ratings (Elo present;
FPI/SP+ null) and are not an allowlisted modeling contract. M06 deferred all
rating adapters, so the matrix must ship without Elo/FPI/SP+ or
rating-versus-market features while remaining extensible for a later
rating-family PR.

## Goals

1. Emit one versioned row per game with target and **approved** pregame features
   only (`matrix_schema_version = "1.0.0"`).
2. Include market, site/schedule/conference, predeclared early-season
   indicators, chronological history (entering record, previous result, SOS,
   rest), and Pick’em sampling-frame labels/metadata where verified.
3. Emit manifest (input hashes, provenance), missingness, and exclusion reports.
4. Record rating availability in the **manifest inventory** as deferred (cite
   M06 memo + reason)—**not** as permanently null matrix columns.
5. Provide one rebuild command; every matrix column documented in schema docs.
6. Guarantee M08 can depend only on the M07 allowlist.
7. Test that deferred rating fields (including `elo_home` / `elo_away`, FPI,
   SP+, rating-vs-market names) never enter the approved matrix.

## Non-goals

- Rating adapters or Elo/FPI/SP+ columns in the matrix
- Scaling, imputation, or model-specific complete-case filtering in the shared
  build
- Poll ranks, coaching, QB, rivalry, travel distance, weather
- Changing production weekly recommend behavior
- Deleting Elo from existing processed/raw research artifacts

## Approach

**Dedicated matrix builder (Approach 2):** project/enrich processed season
inputs into an allowlisted matrix; add rest via chronological shifts; never
select deferred rating columns from inputs.

## Column policy (`matrix_schema_version` 1.0.0)

### Include

| Group | Columns |
|---|---|
| Identity / target / provenance | `game_id`, `season`, `week`, `season_type`, `kickoff_utc`, `source_snapshot`, `home_win` |
| Teams / site / conference | `home_team_id`, `away_team_id`, `home_team`, `away_team`, `home_conference`, `away_conference`, `home_classification`, `away_classification`, `neutral_site`, `is_home` |
| Early-season indicators | `is_week_1`, `is_weeks_1_3` |
| Market (M04) | `spread_home`, `total`, `home_moneyline`, `away_moneyline`, `line_provider_count`, `home_implied_prob`, `home_market_logit`, `spread_home_open`, `total_open`, `spread_move_home`, `total_move`, `market_timing`, `post_kick_provider_quotes_rejected`, `moneyline_fabricated_from_spread` |
| History | `home_entering_wins`, `home_entering_losses`, `away_entering_wins`, `away_entering_losses`, `home_previous_result`, `away_previous_result`, `home_sos`, `away_sos`, `home_days_rest`, `away_days_rest` |
| Pick’em | `sampling_frame`, `verification_status`, `match_status`, `is_pickem_game`, `espn_home_pick_pct`, `espn_expert_home_pct` |

### Semantics

- **`is_home`:** `1` if `neutral_site` is false, else `0` (explicit modeling flag).
- **`is_week_1` / `is_weeks_1_3`:** predeclared from `week`; aligned with eval
  slices; no fitted interactions in v1.
- **Movement fields:** only when labeled open + consensus close exist; otherwise
  null. Never invent open/close from array order (`docs/market_contract.md`).
- **History / rest:** chronological order by `kickoff_utc` then `game_id`.
  Features for a row use only prior **completed** same-season games for that
  team. `*_days_rest` = whole days between prior completed kickoff and this
  kickoff; null if no prior completed game. Incomplete games and ties do not
  update records (same rules as existing `attach_history_features`).
- **Pick’em:** default `sampling_frame=all_fbs` when unknown; verified labels
  only via existing registry/import contract.
- **Team names:** display only; joins prefer team IDs when present.

### Exclude from matrix rows

- `elo_home`, `elo_away`, `fpi_*`, `sp_*`
- Any rating-versus-market / disagreement features
- Poll ranks (`ap_*`, `coaches_*`, `cfp_*`) in v1
- Coaching, QB, rivalry, travel, weather

### Extensibility

A future approved rating-family PR bumps `matrix_schema_version`, appends
versioned columns to the allowlist, updates schema docs, and clears/updates the
manifest deferred entry for that family. No placeholder null rating columns in
1.0.0.

## Manifest rating inventory

Machine-readable block (illustrative):

```json
"ratings_inventory": {
  "elo": {
    "status": "deferred",
    "ref": "docs/ratings_feasibility.md",
    "reason": "M06: no publication timestamp; adapter implementation deferred"
  },
  "fpi": {
    "status": "deferred",
    "ref": "docs/ratings_feasibility.md",
    "reason": "M06: CFBD season-level only; omit until weekly PIT archive"
  },
  "sp": {
    "status": "deferred",
    "ref": "docs/ratings_feasibility.md",
    "reason": "M06: CFBD season-level only; omit until weekly PIT archive"
  }
}
```

Absence of rating columns in the matrix is intentional, not silent omission.

## Architecture

```text
processed season CSVs (or build-on-demand)
        │
        ▼
features/matrix_schema.py   APPROVED_MATRIX_COLUMNS + version
features/matrix.py          load → enrich rest/indicators → project → write
        │
        ├── games_matrix_v1.csv (or per-season + concat)
        ├── matrix_manifest.json
        ├── matrix_missingness.csv
        └── matrix_exclusions.csv
```

- Single allowlist module is the only approved-feature source of truth (builder,
  tests, future M08).
- Matrix builder must not import or pass through Elo/FPI/SP+ into outputs.
- Research Elo may remain on existing processed/raw paths outside this contract.

## Artifacts & CLI

| Artifact | Role |
|---|---|
| Matrix CSV | Allowlisted columns only, stable header order |
| `matrix_manifest.json` | schema version, seasons, row counts, input hashes, snapshot IDs, ratings inventory, build timestamp |
| `matrix_missingness.csv` | Per-column null counts/rates on retained rows |
| `matrix_exclusions.csv` | Dropped `game_id` + reason |

CLI shape:

```bash
pick-prophet matrix --input-dir data/processed --seasons 2017-2025 --output-dir data/processed/matrix
```

Processed matrix outputs remain gitignored; CI uses synthetic fixtures.

## Tests and acceptance

- Future-result mutation cannot alter earlier history/rest features.
- Rest: null on first completed prior; correct day deltas thereafter; season
  isolation.
- Neutral / `is_home` consistency.
- Deterministic rebuild (row order + content hashes stable).
- Movement null when open missing.
- Header order matches allowlist.
- **Hard gate:** approved allowlist and emitted matrix contain none of
  `elo_home`, `elo_away`, `fpi_home`, `fpi_away`, `sp_home`, `sp_away`, or
  rating-vs-market column name patterns.
- Every matrix column defined in schema docs.
- Roadmap M07 marked implemented after acceptance; note ratings deferred via
  manifest.

## Docs updates

- Matrix column definitions (`docs/schema.md` section and/or
  `docs/matrix_schema.md` with pointer).
- Roadmap § M07 status after ship.
- Short pointer from `docs/data_sources.md` / methodology if needed (no scope
  creep).

## Open follow-ups (out of M07)

- Rating-family adapter PRs after M06 human review → schema bump.
- M08 market-residual logistic on allowlisted columns only.
- Optional later inclusion of poll ranks under their own PIT review.
