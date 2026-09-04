# M07 Feature Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a versioned, role-allowlisted leakage-safe modeling matrix (schema 1.0.0) without deferred ratings, with recomputed history/rest, deterministic manifests, and M08-safe baseline/predictor contracts.

**Architecture:** `matrix_schema.py` owns disjoint role lists and header order; `matrix.py` loads processed season CSVs, validates structural identity, recomputes all history/rest chronologically, derives indicators, projects into the ordered role union, and writes matrix + missingness + exclusions + deterministic manifest + volatile run envelope. CLI `pick-prophet matrix` is the single rebuild entrypoint.

**Tech Stack:** Python 3.11+, stdlib csv/json/hashlib/datetime, pytest; pandas optional only if already used for similar loaders (prefer stdlib/dict rows for determinism).

**Spec:** `docs/superpowers/specs/2026-09-04-m07-feature-matrix-design.md`

## Global Constraints

- `matrix_schema_version = "1.0.0"`
- Role lists pairwise disjoint; header = ordered union of IDENTIFIER → TARGET → BASELINE_INPUT → MODEL_FEATURE → AUDIT_SLICE
- No `elo_*`, `fpi_*`, `sp_*`, rating-vs-market, or poll columns in any role list or emitted matrix
- Ratings deferred only in `ratings_inventory` (cite `docs/ratings_feasibility.md`)
- Recompute history/rest inside M07; never trust/pass through processed history fields
- `*_days_rest = floor((current_kickoff - prior_kickoff).total_seconds() / 86400)`; null if no prior completed game; reject non-positive intervals
- No scaling/imputation/complete-case filtering in shared build
- Retain ordinary missingness and null-target rows; exclude only structural failures
- Booleans CSV as `true`/`false`; nulls empty; timestamps UTC ISO-8601; Pick’em % as percentage points `[0, 100]`
- Rows sorted by `(kickoff_utc, game_id)`
- Deterministic: matrix, missingness, exclusions, manifest (sorted JSON keys, compact separators); volatile time only in `matrix_run.json`
- M08 may use only `BASELINE_INPUT_COLUMNS` as offset and `MODEL_FEATURE_COLUMNS` as adjustment predictors
- Identity for exclusions: require `game_id`, `season`, `week`, parseable `kickoff_utc`, and for each side either non-null `*_team_id` **or** non-empty `*_team` name
- No new third-party dependencies

## File map

| File | Role |
|---|---|
| `src/pick_prophet/features/matrix_schema.py` | Version, role tuples, ordered header, disjointness helpers, forbidden-name patterns |
| `src/pick_prophet/features/matrix_history.py` | Authoritative chronological history + rest (or colocated in `matrix.py` if small) |
| `src/pick_prophet/features/matrix.py` | Load, validate, build, write artifacts |
| `src/pick_prophet/cli.py` | `matrix` subcommand |
| `tests/test_matrix_schema.py` | Roles, disjoint, no ratings, M08 surface |
| `tests/test_matrix_history.py` | Leakage, rest, season/postseason |
| `tests/test_matrix_build.py` | Projection, exclusions, determinism, adversarial columns |
| `tests/fixtures/matrix/` | Synthetic processed-like CSVs |
| `docs/matrix_schema.md` | Per-column role/type/null/units/timing/domain |
| `docs/schema.md` | Pointer to matrix schema |
| `docs/modeling_implementation_roadmap.md` | M07 done; M08 rating variants conditional |

---

### Task 1: Schema roles + hard gates

**Files:**
- Create: `src/pick_prophet/features/matrix_schema.py`
- Create: `tests/test_matrix_schema.py`

**Interfaces:**
- Produces:
  - `MATRIX_SCHEMA_VERSION: str = "1.0.0"`
  - `IDENTIFIER_COLUMNS`, `TARGET_COLUMNS`, `BASELINE_INPUT_COLUMNS`, `MODEL_FEATURE_COLUMNS`, `AUDIT_SLICE_COLUMNS` as `tuple[str, ...]`
  - `MATRIX_COLUMNS: tuple[str, ...]` ordered union
  - `assert_roles_disjoint() -> None`
  - `FORBIDDEN_MATRIX_SUBSTRINGS` / `assert_no_deferred_ratings(columns: Iterable[str]) -> None`
  - `m08_baseline_columns()` / `m08_predictor_columns()` aliases returning the two allowlists

Exact column membership must match the spec Include table (including `home_field_advantage`, not `is_home`).

- [ ] **Step 1: Write failing tests**

```python
from pick_prophet.features.matrix_schema import (
    AUDIT_SLICE_COLUMNS,
    BASELINE_INPUT_COLUMNS,
    IDENTIFIER_COLUMNS,
    MATRIX_COLUMNS,
    MATRIX_SCHEMA_VERSION,
    MODEL_FEATURE_COLUMNS,
    TARGET_COLUMNS,
    assert_no_deferred_ratings,
    assert_roles_disjoint,
)

def test_version_and_header_order():
    assert MATRIX_SCHEMA_VERSION == "1.0.0"
    assert MATRIX_COLUMNS == (
        *IDENTIFIER_COLUMNS,
        *TARGET_COLUMNS,
        *BASELINE_INPUT_COLUMNS,
        *MODEL_FEATURE_COLUMNS,
        *AUDIT_SLICE_COLUMNS,
    )

def test_roles_disjoint():
    assert_roles_disjoint()

def test_no_ratings_in_any_role():
    assert_no_deferred_ratings(MATRIX_COLUMNS)

def test_m08_surfaces_exclude_audit_and_target():
    for col in ("home_win", "espn_home_pick_pct", "market_timing", "source_snapshot",
                "game_id", "home_team"):
        assert col not in MODEL_FEATURE_COLUMNS
        assert col not in BASELINE_INPUT_COLUMNS
    assert BASELINE_INPUT_COLUMNS == ("home_implied_prob", "home_market_logit")
```

- [ ] **Step 2: Run tests (expect fail)** → implement schema module → pass

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
Add M07 matrix role allowlists and rating exclusion gates.

Define disjoint identifier/target/baseline/predictor/audit columns for
schema 1.0.0 without deferred rating fields.
EOF
)"
```

---

### Task 2: Chronological history + rest

**Files:**
- Create: `src/pick_prophet/features/matrix_history.py`
- Create: `tests/test_matrix_history.py`
- Create: `tests/fixtures/matrix/history_games.json` (or inline dicts in tests)

**Interfaces:**
- Consumes: list of game dicts with `game_id`, `season`, `season_type`, `week`, `kickoff_utc`, team ids/names, `home_win`
- Produces: `attach_matrix_history(rows: list[dict]) -> None` mutating in place with entering W-L, previous result, SOS, days_rest
- Does **not** read any pre-existing `home_entering_*` / `*_days_rest` from input (overwrite)

Rules from spec: sort by kickoff then game_id; completed wins/losses only; ties/incomplete skip record update; rest floor-seconds/86400; reject ≤0 rest with explicit error or exclusion reason when both kickoffs parse; regular may inform postseason; future mutation test.

- [ ] **Step 1: Failing leakage + rest tests**

```python
def test_future_result_mutation_does_not_change_earlier_rest_or_record():
    ...

def test_rest_null_without_prior_completed_game():
    ...

def test_rest_floor_day_delta_and_rejects_non_positive():
    ...

def test_regular_feeds_postseason_but_not_reverse():
    ...

def test_ignores_stale_history_columns_on_input():
    # input has wrong home_entering_wins; output recomputed
    ...
```

- [ ] **Step 2: Implement → pytest pass → commit**

```bash
git commit -m "$(cat <<'EOF'
Recompute matrix history and rest chronologically for M07.

Overwrite any processed history fields and reject non-positive rest
intervals using kickoff-as-proxy timing.
EOF
)"
```

---

### Task 3: Matrix builder core (project, exclude, missingness)

**Files:**
- Create: `src/pick_prophet/features/matrix.py`
- Create: `tests/test_matrix_build.py`
- Create: `tests/fixtures/matrix/games_2099.csv` (synthetic processed-like with extra `elo_home` column)

**Interfaces:**
- `load_season_csv(path: Path) -> list[dict]`
- `validate_and_partition(rows, *, season, snapshot) -> tuple[retained, exclusions]`
- `derive_indicators(row) -> None` (`is_week_1`, `is_weeks_1_3`, `home_field_advantage`)
- `project_row(row) -> dict` only `MATRIX_COLUMNS`
- `build_matrix(input_paths: list[Path], ...) -> MatrixBuildResult`
- `write_matrix_csv`, `write_missingness`, `write_exclusions`
- Exclusion reason codes e.g. `missing_game_id`, `missing_kickoff`, `missing_home_identity`, `missing_away_identity`, `invalid_week`, `invalid_season`

- [ ] **Step 1: Tests**

```python
def test_extra_elo_column_stripped_from_output():
    ...

def test_adversarial_columns_cannot_enter_model_features():
    # inject target copy, poll, public pct into input wide table
    ...

def test_ordinary_missing_market_retains_row():
    ...

def test_structural_missing_kickoff_excluded_with_reason():
    ...

def test_duplicate_game_id_raises():
    ...

def test_header_equals_matrix_columns():
    ...
```

- [ ] **Step 2: Implement builder → pass → commit**

```bash
git commit -m "$(cat <<'EOF'
Build allowlisted M07 feature matrix with structural exclusions.

Project role columns only, strip deferred ratings, and retain ordinary
feature missingness without complete-case filtering.
EOF
)"
```

---

### Task 4: Manifest, run envelope, CLI, determinism

**Files:**
- Modify: `src/pick_prophet/features/matrix.py`
- Modify: `src/pick_prophet/cli.py`
- Modify: `tests/test_matrix_build.py`

**Interfaces:**
- `write_manifest(...)` deterministic JSON (no timestamp)
- `write_run_envelope(...)` volatile `generated_at_utc`
- `sha256_file(path) -> str`
- `run_matrix_cli` / `build_and_write(input_dir, seasons, output_dir)`
- CLI: `pick-prophet matrix --input-dir --seasons --output-dir`
- Manifest includes `ratings_inventory` per spec, reconciled counts, input hashes, output hashes of matrix/missingness/exclusions (not self-hash)

- [ ] **Step 1: Determinism tests** — two builds equal bytes for matrix/missingness/exclusions/manifest; `matrix_run.json` may differ on timestamp only

- [ ] **Step 2: Wire CLI → smoke with fixtures → commit**

```bash
git commit -m "$(cat <<'EOF'
Add matrix CLI with deterministic manifest and volatile run metadata.

Record deferred ratings in inventory and hash deterministic outputs for
reproducible M07 rebuilds.
EOF
)"
```

---

### Task 5: Docs, roadmap M07/M08 note, PR

**Files:**
- Create: `docs/matrix_schema.md` (every column: role, type, CSV repr, null, units, timing, domain)
- Modify: `docs/schema.md` (pointer)
- Modify: `docs/modeling_implementation_roadmap.md` (§ M07 status; § M08 rating variants conditional on schema bump)
- Optional short pointer in `docs/data_sources.md` or methodology

- [ ] **Step 1: Write docs matching schema 1.0.0**

- [ ] **Step 2: Full pytest + ruff**

- [ ] **Step 3: Commit + open PR from `modeling/m07-feature-matrix`**

Title: `Leakage-safe modeling feature matrix (M07)`

Body must state: no Elo/FPI/SP+ in matrix; history recomputed; role allowlists for M08; ratings deferred in manifest.

```bash
git commit -m "$(cat <<'EOF'
Document M07 matrix schema and mark roadmap status complete.

Point schema docs at role allowlists and note M08 rating variants wait
on a future approved matrix schema bump.
EOF
)"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|---|---|
| Role allowlists + disjoint header | Task 1 |
| No deferred ratings in matrix | Tasks 1, 3 |
| Recompute history/rest | Task 2 |
| Market/movement/indicators/Pick’em audit | Task 3 |
| Retention vs structural exclusions | Task 3 |
| Manifest inventory + hashes + run.json | Task 4 |
| CLI rebuild | Task 4 |
| M08 baseline/predictor tests | Tasks 1, 3 |
| Docs + M08 roadmap caveat | Task 5 |
| Identity exclusion rule (id or name) | Task 3 (Global Constraints) |
| Pick’em % domain [0,100] | Tasks 3–5 serialization docs |

No TBD placeholders remain in task steps.
