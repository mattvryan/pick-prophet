# M06 Ratings Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a source-feasibility memo plus a read-only Elo pregame-vs-weekly comparison harness (CI fixtures + acceptance regeneration), with adapter implementation deferred.

**Architecture:** A research-only module aggregates season×week Elo agreement from CFBD snapshot JSON; synthetic fixtures drive pytest; operators regenerate committed aggregate CSV + provenance JSON from local raw trees. The feasibility memo documents CFBD Elo/FPI/SP+, sportsdataverse weekly FPI, and weekly SP+ archive options with implement / investigate further / omit recommendations. No production joins or dependencies.

**Tech Stack:** Python 3.11+, stdlib `json`/`csv`/`hashlib`/`statistics`, pytest; existing local `data/raw/cfbd/` snapshots for acceptance only.

**Spec:** `docs/superpowers/specs/2026-09-04-m06-ratings-feasibility-design.md`

## Global Constraints

- No changes to `src/pick_prophet/features/build.py` join logic
- No new third-party package dependencies
- No production adapters; no weekly-card CLI wiring for ratings joins
- No row-level Elo comparison dumps committed to git
- Roadmap M06 status must read exactly: **M06 feasibility memo complete; adapter implementation deferred.**
- Numeric Elo agreement does **not** prove publication timing relative to kickoff (memo must state this)
- Absence of a documented license restriction is **not** permission to redistribute
- Every factual memo claim about endpoints/licensing/revision cites a primary source when available; otherwise label `inference` or `unknown`
- Canonical weekly Elo lookup prefers `(season, season_type, week, team_id)`; audited normalized team-name fallback only when team_id is absent on the weekly row (observed CFBD `/ratings/elo` payloads today expose `team`/`week`/`year`/`elo`/`conference` only — document this)
- Duplicate weekly keys: identical values may dedupe with audited count; conflicting values must raise or be explicitly excluded (never silent last-wins)
- Aggregate CSV columns and provenance fields are mandatory as listed in Task 1–2
- Figures optional; omit unless Week 1 pattern is unclear from tables

## File map

| File | Role |
|---|---|
| `src/pick_prophet/research/__init__.py` | Package marker; empty or minimal exports |
| `src/pick_prophet/research/elo_pregame_vs_weekly.py` | Load, compare, aggregate, write CSV/provenance |
| `tests/fixtures/ratings_elo_compare/games.json` | Synthetic games (Week 1, mid-season, postseason, multi-season) |
| `tests/fixtures/ratings_elo_compare/elo.json` | Synthetic weekly Elo (incl. week 0/missing, duplicates) |
| `tests/test_elo_pregame_vs_weekly.py` | CI unit tests |
| `docs/ratings_feasibility.md` | Canonical memo + recommendations |
| `docs/ratings_elo_pregame_vs_weekly.csv` | Committed aggregate (acceptance output) |
| `docs/ratings_elo_pregame_vs_weekly.provenance.json` | Mandatory provenance sidecar |
| `docs/modeling_implementation_roadmap.md` | M06 status line |
| `docs/data_sources.md` | Short pointer to memo |
| `docs/schema.md` | Document current `elo_home`/`elo_away` preference (docs only) |

---

### Task 1: Comparison harness + synthetic fixtures (TDD)

**Files:**
- Create: `src/pick_prophet/research/__init__.py`
- Create: `src/pick_prophet/research/elo_pregame_vs_weekly.py`
- Create: `tests/fixtures/ratings_elo_compare/games.json`
- Create: `tests/fixtures/ratings_elo_compare/elo.json`
- Create: `tests/test_elo_pregame_vs_weekly.py`

**Interfaces:**
- Consumes: CFBD-shaped game/elo JSON dicts (camelCase or snake_case via existing `_get`-style dual keys)
- Produces:
  - `DEFAULT_TOLERANCE: float = 1.0`
  - `load_games(path: Path) -> list[dict]`
  - `load_weekly_elo(path: Path) -> WeeklyEloIndex` where index maps `EloKey` → `float` and exposes audit counters
  - `EloKey = namedtuple/dataclass(season: int, season_type: str, week: int, team_key_type: Literal["id","name"], team_key: str | int)`
  - `compare_snapshot(games, weekly_index, *, tolerance: float) -> list[SideCompare]` (in-memory only)
  - `aggregate_sides(sides: list[SideCompare]) -> list[dict]` season×season_type×week rows
  - `write_aggregate_csv(rows: list[dict], path: Path) -> None`
  - `sha256_file(path: Path) -> str`
  - `ConflictError(Exception)` for conflicting duplicate weekly keys

**Aggregate CSV columns (exact header order):**

```text
season,season_type,week,n_sides,n_both_present,n_exact_match,exact_match_rate,n_within_tolerance,within_tolerance_rate,mean_abs_delta,median_abs_delta,p90_abs_delta,p95_abs_delta,max_abs_delta,n_pregame_null,pregame_null_rate,n_weekly_null,weekly_null_rate,n_pregame_only,n_weekly_only,n_name_fallback_joins
```

Rates are `None`/empty when denominator is 0. Deltas computed only on sides where both values are present.

- [ ] **Step 1: Write synthetic fixtures**

`tests/fixtures/ratings_elo_compare/games.json` — include at least:

1. Season 2099 regular week 1: home has pregame Elo, away missing (tests `feature_week=0`)
2. Season 2099 regular week 5: both sides present; home matches weekly week 4; away mismatches by 5
3. Season 2099 postseason week 1: must **not** join to regular week-0/week-1 Elo
4. Season 2098 regular week 3: multi-season isolation
5. One FCS-only game (both classifications non-fbs) that the loader **skips**
6. Games expose `id`, `season`, `week`, `seasonType`, `startDate`, `homeId`/`awayId`, `homeTeam`/`awayTeam`, `homeClassification`/`awayClassification`, `homePregameElo`/`awayPregameElo`

`tests/fixtures/ratings_elo_compare/elo.json` — include:

1. Week 0 and week 1 rows for 2099 (preseason semantics)
2. Week 4 rows matching/mismatching the week-5 game
3. Two **identical** duplicate rows for the same `(year, week, team)` (audit dedupe)
4. Two **conflicting** duplicate rows for another team (must raise on load)
5. A 2098 week-2 row for multi-season
6. Optional `seasonType` omitted (treat default `season_type="regular"`)
7. No `teamId` on most rows; one optional row **with** `teamId` if you want an id-key path in CI (otherwise name-only is fine if tests cover name fallback)

- [ ] **Step 2: Write failing tests**

```python
# tests/test_elo_pregame_vs_weekly.py
from pathlib import Path
import pytest
from pick_prophet.research.elo_pregame_vs_weekly import (
    DEFAULT_TOLERANCE,
    ConflictError,
    aggregate_sides,
    compare_snapshot,
    load_games,
    load_weekly_elo,
)

FIX = Path(__file__).parent / "fixtures" / "ratings_elo_compare"


def test_week1_uses_feature_week_zero_and_counts_nulls():
    games = load_games(FIX / "games.json")
    weekly = load_weekly_elo(FIX / "elo.json")  # fixture without conflicting dups
    sides = compare_snapshot(games, weekly, tolerance=DEFAULT_TOLERANCE)
    rows = { (r["season"], r["season_type"], r["week"]): r for r in aggregate_sides(sides) }
    w1 = rows[(2099, "regular", 1)]
    assert w1["n_sides"] >= 2
    assert w1["n_weekly_null"] >= 1 or w1["n_both_present"] >= 1  # depends on week-0 presence


def test_midseason_exact_vs_tolerance_metrics():
    ...


def test_postseason_isolated_from_regular_week_numbers():
    ...


def test_multi_season_isolation():
    ...


def test_identical_duplicates_deduped_with_audit():
    ...


def test_conflicting_duplicates_raise():
    with pytest.raises(ConflictError):
        load_weekly_elo(FIX / "elo_conflict.json")  # or inline temp file


def test_fbs_filter_skips_lower_division_only():
    ...
```

Split conflicting-duplicate Elo into `elo_conflict.json` if keeping the happy-path `elo.json` loadable.

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_elo_pregame_vs_weekly.py -v`
Expected: FAIL (import/module missing)

- [ ] **Step 4: Implement minimal harness**

Implement in `elo_pregame_vs_weekly.py`:

```python
DEFAULT_TOLERANCE = 1.0
DEFAULT_SEASON_TYPE = "regular"

def _get(row, *keys):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None

def load_games(path: Path) -> list[dict]:
    # Keep games with at least one classification == "fbs" (same rule as build.py)
    # Normalize fields to snake_case keys used by compare_snapshot

def load_weekly_elo(path: Path) -> WeeklyEloIndex:
    # Build map keyed by EloKey
    # Prefer team_id when present; else team_key_type="name" with stripped team string
    # season_type from payload or DEFAULT_SEASON_TYPE
    # Identical duplicate values: keep one, increment identical_duplicate_count
    # Conflicting values for same EloKey: raise ConflictError

def compare_snapshot(games, weekly, *, tolerance: float) -> list[SideCompare]:
    # For each game side (home/away):
    #   feature_week = max(week - 1, 0)
    #   Lookup weekly at (season, game.season_type, feature_week, id preferred else name)
    #   Never cross season or season_type
    #   Record join_key_type used

def aggregate_sides(sides) -> list[dict]:
    # Group by (season, season_type, week) of the *game* (not feature_week)
    # Compute metrics listed above; sort rows by season, season_type, week
```

Percentiles: use `statistics.quantiles` or a small deterministic helper; document method in provenance (`percentile_method`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_elo_pregame_vs_weekly.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/pick_prophet/research tests/fixtures/ratings_elo_compare tests/test_elo_pregame_vs_weekly.py
git commit -m "$(cat <<'EOF'
Add research harness for Elo pregame vs weekly comparison.

Synthetic fixtures cover Week 1, postseason isolation, and duplicate
handling without touching production rating joins.
EOF
)"
```

---

### Task 2: Provenance writer + acceptance entrypoint

**Files:**
- Modify: `src/pick_prophet/research/elo_pregame_vs_weekly.py`
- Modify: `tests/test_elo_pregame_vs_weekly.py`
- Create: optional `python -m pick_prophet.research.elo_pregame_vs_weekly` via `if __name__ == "__main__"` (do **not** add a production `pick-prophet` subcommand)

**Interfaces:**
- Consumes: Task 1 functions
- Produces:
  - `write_aggregate_csv(rows, path) -> None`
  - `build_provenance(*, snapshot_paths: list[Path], seasons, season_types, tolerance, helper_path, rows_in, rows_out, exclusions, identical_duplicate_count, conflicting_duplicate_count, parameters: dict) -> dict`
  - `write_provenance(doc: dict, path: Path) -> None`
  - `select_latest_snapshots(raw_cfbd_root: Path, seasons: list[int]) -> dict[int, Path]` — deterministic rule: for each season directory, choose the lexicographically maximum child directory name that contains both `games.json` and `elo.json`
  - `run_acceptance(raw_root, seasons, out_csv, out_prov, tolerance) -> None`

**Provenance JSON required keys:**

```text
generated_at_utc
repository_revision  (git rev-parse HEAD, or null if unavailable)
helper_module
helper_sha256
tolerance
percentile_method
snapshot_selection_rule
snapshots: [{season, path, games_sha256, elo_sha256}]
seasons
season_types
parameters
input_game_rows
input_side_rows
output_aggregate_rows
exclusions
identical_duplicate_count
conflicting_duplicate_count  (0 when conflicts raise)
notes
```

- [ ] **Step 1: Write failing tests for CSV header + provenance keys**

```python
def test_write_aggregate_csv_header_and_roundtrip(tmp_path):
    ...

def test_provenance_contains_required_keys(tmp_path):
    doc = build_provenance(...)
    for key in REQUIRED:
        assert key in doc

def test_select_latest_snapshots_picks_max_dirname(tmp_path):
    # create season/older and season/newer with games.json+elo.json
    ...
```

- [ ] **Step 2: Run to verify fail / then implement writers + `__main__`**

CLI shape (acceptance only):

```bash
python -m pick_prophet.research.elo_pregame_vs_weekly \
  --raw-root data/raw/cfbd \
  --seasons 2017,2018,2019,2020,2021,2022,2023,2024,2025 \
  --output-csv docs/ratings_elo_pregame_vs_weekly.csv \
  --output-provenance docs/ratings_elo_pregame_vs_weekly.provenance.json \
  --tolerance 1.0
```

- [ ] **Step 3: pytest pass + commit**

```bash
git add src/pick_prophet/research/elo_pregame_vs_weekly.py tests/test_elo_pregame_vs_weekly.py
git commit -m "$(cat <<'EOF'
Add Elo comparison provenance and acceptance entrypoint.

Operators can regenerate aggregate CSV from local CFBD snapshots without
wiring a production CLI subcommand.
EOF
)"
```

---

### Task 3: Local acceptance run (aggregate artifacts)

**Files:**
- Create/update: `docs/ratings_elo_pregame_vs_weekly.csv`
- Create/update: `docs/ratings_elo_pregame_vs_weekly.provenance.json`

**Interfaces:**
- Consumes: Task 2 `run_acceptance` / module CLI
- Produces: committed aggregate + provenance for memo Task 4

- [ ] **Step 1: Run acceptance against local raw tree**

```bash
python -m pick_prophet.research.elo_pregame_vs_weekly \
  --raw-root data/raw/cfbd \
  --seasons 2017,2018,2019,2020,2021,2022,2023,2024,2025 \
  --output-csv docs/ratings_elo_pregame_vs_weekly.csv \
  --output-provenance docs/ratings_elo_pregame_vs_weekly.provenance.json \
  --tolerance 1.0
```

Expected: CSV with one row per observed `(season, season_type, week)`; provenance lists each snapshot path + hashes.

If a season snapshot is missing, fail loudly listing the season (do not silently skip unless `--allow-missing-seasons` is explicitly implemented and documented — prefer fail-fast for M06).

- [ ] **Step 2: Spot-check Week 1 rows**

Confirm week-1 groups show elevated `n_weekly_null` and/or `n_pregame_only` if week-0 weekly Elo is absent in raw payloads (local 2017–2024 Elo weeks start at 1 — document that observation in the memo).

- [ ] **Step 3: Commit artifacts only (no row-level dump)**

```bash
git add docs/ratings_elo_pregame_vs_weekly.csv docs/ratings_elo_pregame_vs_weekly.provenance.json
git commit -m "$(cat <<'EOF'
Commit Elo pregame-vs-weekly aggregate comparison artifacts.

Season/week summaries and provenance only; no row-level dumps.
EOF
)"
```

---

### Task 4: Feasibility memo

**Files:**
- Create: `docs/ratings_feasibility.md`

**Interfaces:**
- Consumes: aggregate CSV + provenance; CFBD API docs; sportsdataverse/cfbfastR docs; SP+ archive search notes
- Produces: memo with full 9-point checklist per source + Elo canonical recommendation for *future* adapters

- [ ] **Step 1: Write memo structure**

Required sections:

1. Purpose / non-goals / hard interpretation rule (agreement ≠ publication time)
2. Current production Elo behavior (cite `build.py` lines conceptually; do not edit it)
3. Empirical Elo comparison summary (link CSV + provenance; Week 1 / preseason subsection with numbers)
4. Source dossiers (each with items 1–9 from the spec):
   - CFBD Elo (game pregame + `/ratings/elo`)
   - CFBD FPI (`/ratings/fpi`)
   - CFBD SP+ (`/ratings/sp`)
   - sportsdataverse weekly FPI (docs only; no package install)
   - Credible weekly SP+ archive (state none PIT-safe if search finds only season-end or retroactively revised pages)
5. Recommendation table
6. Follow-up adapter branch naming guidance (`data/m06b-elo-adapter`, etc.) after human review

Primary citations to prefer:

- CFBD OpenAPI / swagger for query params (`week` on Elo only)
- CFBD terms / API key pages for redistribution (label `unknown` if terms do not clearly allow republishing derived tables)
- sportsdataverse-data / cfbfastR `load_cfb_fpi_weekly` docs for contemporaneous vs retrospective flags
- Publisher/SB Nation/FO pages only as leads; do not claim PIT safety without as-of timestamps

- [ ] **Step 2: Fill recommendations (decision guide for authors)**

Use evidence; do not invent. Expected *direction* (confirm or revise with citations):

| Source | Likely recommendation | Why to verify |
|---|---|---|
| CFBD game pregame Elo | `implement` or `investigate further` | Game-scoped; still lacks explicit `published_at` |
| CFBD weekly Elo | `implement` as fallback or `investigate further` | Weekly param exists; name-keyed; week-0 often missing |
| CFBD FPI | `omit` (season-level) | No week param in public API |
| CFBD SP+ | `omit` (season-level) | Same |
| sportsdataverse weekly FPI | `investigate further` | Has weekly as-of metadata; licensing/redistribution + dependency policy unresolved |
| Other weekly SP+ | `omit` or `investigate further` | Only if a timestamped reproducible archive is identified |

Elo canonical recommendation must pick one preferred future surface (or `investigate further`) and state remaining timing gaps explicitly.

- [ ] **Step 3: Commit**

```bash
git add docs/ratings_feasibility.md
git commit -m "$(cat <<'EOF'
Add ratings source feasibility memo for M06.

Document temporal semantics and per-source implement/investigate/omit
recommendations without shipping adapters.
EOF
)"
```

---

### Task 5: Docs cross-links, roadmap, schema, PR

**Files:**
- Modify: `docs/modeling_implementation_roadmap.md` § M06
- Modify: `docs/data_sources.md`
- Modify: `docs/schema.md` (`elo_home` / `elo_away` description only)
- Verify: `git diff -- src/pick_prophet/features/build.py` is empty

- [ ] **Step 1: Update roadmap M06 status**

Set status line to exactly:

```markdown
**Status:** M06 feasibility memo complete; adapter implementation deferred.
```

Keep adapter implementation bullets unchecked / deferred; point to `docs/ratings_feasibility.md`.

- [ ] **Step 2: Update `docs/data_sources.md`**

Add a short pointer under ratings limitations:

```markdown
- Ratings feasibility and temporal semantics (M06 memo): see
  `docs/ratings_feasibility.md`. Adapter decisions are deferred.
```

- [ ] **Step 3: Update `docs/schema.md` Elo rows**

Replace the vague Elo line with docs-only accuracy, e.g.:

```markdown
| `elo_home`, `elo_away` | float | Prefer game-level CFBD `home_pregame_elo` / `away_pregame_elo` when present; else weekly `/ratings/elo` at week *w−1* joined by team name (audited). Not proof of publication time. See `docs/ratings_feasibility.md`. |
```

Leave FPI/SP+ wording as null-until-archive.

- [ ] **Step 4: Full test suite**

Run: `pytest`
Expected: PASS (including new research tests)

- [ ] **Step 5: Open PR from `data/m06-pit-ratings`**

Title: `Ratings feasibility memo and Elo comparison (M06)`

Body must state: no adapters, no `build.py` join changes, CI uses fixtures, acceptance regenerated aggregate+provenance, roadmap deferred wording.

```bash
git push -u origin HEAD
gh pr create --base main --title "Ratings feasibility memo and Elo comparison (M06)" --body "$(cat <<'EOF'
## Summary
- Feasibility memo for CFBD Elo/FPI/SP+, sportsdataverse weekly FPI, and weekly SP+ archives
- Research-only Elo pregame vs weekly aggregate comparison + provenance
- Roadmap: M06 feasibility memo complete; adapter implementation deferred

## Test plan
- [x] pytest tests/test_elo_pregame_vs_weekly.py
- [x] full pytest
- [x] local acceptance regeneration of aggregate CSV + provenance
- [x] confirm build.py untouched
EOF
)"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|---|---|
| Memo for Elo, FPI, SP+, sportsdataverse FPI, weekly SP+ | Task 4 |
| 9-point checklist + citations / inference labels | Task 4 |
| Aggregate season×week CSV (not row-level) | Tasks 1–3 |
| Mandatory provenance JSON | Task 2–3 |
| Week 1 / preseason analysis | Tasks 1, 3, 4 |
| Agreement ≠ publication-time proof | Task 4 |
| Synthetic CI fixtures + acceptance workflow | Tasks 1–3 |
| No adapters / deps / build.py changes | Global + Task 5 verify |
| Roadmap exact deferred wording | Task 5 |
| schema.md Elo docs-only update | Task 5 |
| Duplicate identical vs conflicting rules | Task 1 |
| team_id preferred; name fallback audited | Task 1 |
| Regular/postseason isolation | Task 1 |

No remaining TBD placeholders in task steps.
