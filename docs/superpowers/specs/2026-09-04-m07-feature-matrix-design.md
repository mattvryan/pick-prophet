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

1. Emit one versioned row per eligible source game with a target, approved
   pregame predictors, baseline inputs, and explicitly separated audit metadata
   (`matrix_schema_version = "1.0.0"`).
2. Include market, site/schedule/conference, predeclared early-season
   indicators, chronological history (entering record, previous result, SOS,
   rest), and Pick’em sampling-frame labels/metadata where verified.
3. Emit manifest (input hashes, provenance), missingness, and exclusion reports.
4. Record rating availability in the **manifest inventory** as deferred (cite
   M06 memo + reason)—**not** as permanently null matrix columns.
5. Provide one rebuild command; every matrix column documented in schema docs.
6. Guarantee M08 can consume predictors only from the M07 predictor allowlist;
   target, identity, provenance, and evaluation metadata are disjoint.
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

**Dedicated matrix builder (Approach 2):** load processed season inputs,
recompute all history and rest fields through one authoritative chronological
routine, derive indicators, and project into role-specific allowlists. Existing
derived history fields in the input are not trusted or passed through. Deferred
rating columns are never selected.

## Column policy (`matrix_schema_version` 1.0.0)

### Column roles and allowlists

`features/matrix_schema.py` defines immutable, pairwise-disjoint lists. Their
ordered union is the matrix header:

- `IDENTIFIER_COLUMNS`: row identity and display labels; never predictors.
- `TARGET_COLUMNS`: outcomes; never predictors.
- `BASELINE_INPUT_COLUMNS`: the market probability/logit consumed by M08 as
  the fixed baseline/offset, not as an unrestricted adjustment feature.
- `MODEL_FEATURE_COLUMNS`: the only columns M08 may use as candidate adjustment
  predictors.
- `AUDIT_SLICE_COLUMNS`: provenance, timing disclosures, sampling-frame labels,
  Pick’em observations, and quality flags; never predictors.

M08 imports `BASELINE_INPUT_COLUMNS` and `MODEL_FEATURE_COLUMNS` directly. It
must not infer predictors from numeric dtype or from all columns remaining after
dropping the target.

### Include

| Group | Columns |
|---|---|
| `IDENTIFIER_COLUMNS` | `game_id`, `season`, `week`, `season_type`, `kickoff_utc`, `home_team_id`, `away_team_id`, `home_team`, `away_team` |
| `TARGET_COLUMNS` | `home_win` |
| `BASELINE_INPUT_COLUMNS` | `home_implied_prob`, `home_market_logit` |
| `MODEL_FEATURE_COLUMNS` — site/conference | `home_conference`, `away_conference`, `home_classification`, `away_classification`, `neutral_site`, `home_field_advantage` |
| `MODEL_FEATURE_COLUMNS` — temporal | `is_week_1`, `is_weeks_1_3` |
| `MODEL_FEATURE_COLUMNS` — market context | `spread_home`, `total`, `home_moneyline`, `away_moneyline`, `line_provider_count`, `spread_home_open`, `total_open`, `spread_move_home`, `total_move` |
| `MODEL_FEATURE_COLUMNS` — history | `home_entering_wins`, `home_entering_losses`, `away_entering_wins`, `away_entering_losses`, `home_previous_result`, `away_previous_result`, `home_sos`, `away_sos`, `home_days_rest`, `away_days_rest` |
| `AUDIT_SLICE_COLUMNS` | `source_snapshot`, `market_timing`, `post_kick_provider_quotes_rejected`, `moneyline_fabricated_from_spread`, `sampling_frame`, `verification_status`, `match_status`, `is_pickem_game`, `espn_home_pick_pct`, `espn_expert_home_pct` |

### Semantics

- **`home_field_advantage`:** `1` if `neutral_site` is false, else `0`. This is
  the home-designated team’s site advantage flag; it is not a generic team-side
  indicator.
- **`is_week_1` / `is_weeks_1_3`:** predeclared from `week`; aligned with eval
  slices; no fitted interactions in v1.
- **Market timing:** observations with a verified `observed_at < kickoff_utc`
  are PIT-verified. Historical CFBD `closing-like` observations without an
  observation timestamp are permitted only under the explicit M04 baseline
  exception and retain
  `market_timing=cfbd_historical_closing_like_no_observation_timestamp`. Their
  inclusion is not evidence that they were available before kickoff.
  `market_timing`, rejected-quote counts, and fabrication flags are audit fields,
  never predictors.
- **Movement fields:** only when labeled open + consensus close exist; otherwise
  null. Never invent open/close from array order (`docs/market_contract.md`).
- **History / rest:** chronological order by `kickoff_utc` then `game_id`.
  Features for a row use only prior **completed** same-season games for that
  team. All history fields are recomputed inside M07 rather than copied from
  processed inputs. `*_days_rest = floor((current_kickoff_utc -
  prior_kickoff_utc).total_seconds() / 86400)` and is null if there is no prior
  completed game. Because source data lacks completion timestamps, the prior
  kickoff is an explicitly documented proxy; reject a non-positive interval.
  Incomplete games and ties do not update records (same record semantics as
  existing `attach_history_features`). Regular games may feed later postseason
  history in the same season, but chronological ordering prevents postseason
  results from affecting regular-season rows.
- **Pick’em:** default `sampling_frame=all_fbs` when unknown; verified labels
  only via existing registry/import contract. Public and expert percentages are
  retained solely for evaluation/review and are prohibited from M08 predictors.
- **Team names:** display only; joins prefer team IDs when present.

### Row retention and exclusions

- The candidate universe is the canonical FBS-game population produced by the
  existing build contract (at least one FBS participant), for the explicitly
  requested seasons.
- Retain rows with ordinary feature missingness. Missing market, movement,
  history, conference, Pick’em, or classification values never trigger shared
  complete-case filtering.
- Retain incomplete games and ties with `home_win=null`; downstream training may
  select rows with a valid binary target, but that target-eligibility filter is
  not a feature-completeness filter.
- Exclude only structurally unusable rows: missing/invalid `game_id`, season,
  week, kickoff, home identity, or away identity. Record the source season,
  snapshot, game ID when available, reason code, and detail.
- Duplicate `game_id` values are a build error, not an order-dependent
  exclusion. Conflicting season/snapshot identity is reported before aborting.
- Reconcile counts in the manifest: `input_rows = retained_rows +
  excluded_rows`. No row disappears silently.

### Excluded columns

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
features/matrix_schema.py   role-specific allowlists + ordered union + version
features/matrix.py          load → validate → recompute history/rest → project → write
        │
        ├── games_matrix_v1.csv (or per-season + concat)
        ├── matrix_manifest.json
        ├── matrix_missingness.csv
        ├── matrix_exclusions.csv
        └── matrix_run.json
```

- The schema module is the only source of truth for column roles, header order,
  baseline inputs, and approved predictors (builder, tests, future M08).
- Assert role lists are pairwise disjoint. The emitted header is their ordered
  union; arbitrary extra input columns cannot enter any role.
- Matrix builder must not import or pass through Elo/FPI/SP+ into outputs.
- Research Elo may remain on existing processed/raw paths outside this contract.

## Artifacts & CLI

| Artifact | Role |
|---|---|
| Matrix CSV | Role-allowlisted columns only, stable header and row order |
| `matrix_manifest.json` | Canonical deterministic payload: schema/role versions, seasons, reconciled row counts, exact input paths and SHA-256 hashes, snapshot IDs, ratings inventory, and hashes of the other deterministic outputs |
| `matrix_missingness.csv` | Per-column null counts/rates on retained rows |
| `matrix_exclusions.csv` | Source season/snapshot, `game_id` when available, stable reason code, detail |
| `matrix_run.json` | Volatile run envelope such as generation timestamp; excluded from deterministic content identity |

CLI shape:

```bash
pick-prophet matrix --input-dir data/processed --seasons 2017-2025 --output-dir data/processed/matrix
```

Processed matrix outputs remain gitignored; CI uses synthetic fixtures.

The matrix schema documentation defines for every column: role, logical type,
CSV representation, null encoding, units, timing semantics, and allowed domain.
Booleans serialize canonically as `true` / `false`, nulls as empty CSV fields,
timestamps as UTC ISO-8601, and percentages as percentage points in `[0, 100]`.
Rows sort by `(kickoff_utc, game_id)`. JSON uses sorted keys and stable compact
separators for hashing. SHA-256 covers exact input bytes and each deterministic
output; the manifest records hashes of the matrix, missingness, and exclusions
but does not recursively record its own hash. The volatile `matrix_run.json`
and its generation time are not included in deterministic content identity.

## Tests and acceptance

- Future-result mutation cannot alter earlier history/rest features.
- Rest: null on first completed prior; correct day deltas thereafter; season
  isolation, regular-to-postseason flow, and rejection of non-positive deltas.
- Neutral / `home_field_advantage` consistency.
- Deterministic rebuild: matrix, missingness, exclusions, canonical manifest
  payload, and their content hashes are stable; volatile run metadata may vary.
- Movement null when open missing.
- Header order matches the ordered role union; all role lists are disjoint.
- Input/retained/excluded counts reconcile; invalid structural rows carry stable
  exclusion reasons, while ordinary feature missingness retains rows.
- **Hard gate:** approved predictor allowlist and emitted matrix contain none of
  `elo_home`, `elo_away`, `fpi_home`, `fpi_away`, `sp_home`, `sp_away`, or
  rating-vs-market column name patterns.
- Adversarial extra inputs—including target copies, ratings, polls, public
  shares, and arbitrary numeric columns—cannot enter `MODEL_FEATURE_COLUMNS`.
- `home_win`, IDs/names, provenance, timing/quality flags, sampling labels, and
  ESPN public/expert percentages are absent from `MODEL_FEATURE_COLUMNS`.
- M08-facing tests prove only `BASELINE_INPUT_COLUMNS` may supply the offset and
  only `MODEL_FEATURE_COLUMNS` may supply adjustment predictors.
- Every matrix column defined in schema docs.
- Roadmap M07 marked implemented after acceptance; note ratings deferred via
  manifest.

## Docs updates

- Matrix column definitions (`docs/schema.md` section and/or
  `docs/matrix_schema.md` with pointer).
- Roadmap § M07 status after ship.
- Update roadmap § M08 so rating-based variants are conditional on a later
  approved matrix schema containing rating features. With schema 1.0.0, M08
  compares the market baseline against approved site, schedule, history,
  temporal, and market-context adjustments only.
- Short pointer from `docs/data_sources.md` / methodology if needed (no scope
  creep).

## Open follow-ups (out of M07)

- Rating-family adapter PRs after M06 human review → schema bump.
- M08 market-residual logistic using only the schema’s baseline and predictor
  roles; rating variants remain conditional on a future approved schema bump.
- Optional later inclusion of poll ranks under their own PIT review.
