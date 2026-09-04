# Weekly artifact contract

Semantics for files under `weekly/YYYY-WNN/`, based on the current repository
implementation and Week 1 layout. Prefer existing schemas; label gaps explicitly.

## Directory conventions

| Path pattern | Role |
|---|---|
| `weekly/YYYY-WNN/` | One contest week |
| `weekly/YYYY-WNN/market/<UTC_STAMP>/` | Immutable market snapshot |
| `weekly/YYYY-WNN/signals/<UTC_STAMP>/` | Immutable ratings/venue snapshot |
| `weekly/YYYY-WNN/recommendations*/` or `output/recommend-*` | Generated baseline recommendation runs |
| `weekly/YYYY-WNN/tiebreaker/` | Generated tiebreaker baseline |

Raw provider JSON under market/signals paths may be gitignored locally; manifests
and derived CSVs are the portable contract.

## Existing artifacts

### `slate.csv`

- **Kind:** input (contest sampling frame)
- **Immutable after capture verification:** treat as append-only / replace only
  with a new verified capture and updated manifest
- **Required timing/provenance:** `captured_at_utc`, `lock_at_utc` per row;
  CFBD IDs when matched
- **Regenerate?** No silent regen. Corrections require an audited rewrite
- **Baseline vs manual:** contains ESPN public % and screenshot odds for
  context; not the final submitted picks

### `capture_manifest.json`

- **Kind:** input provenance
- **Immutable:** yes after capture is accepted
- **Required:** `captured_at_utc`, contest metadata, source filenames/hashes,
  interpretation notes (timezone, away/home orientation, confidence mode)
- **Regenerate?** Only with a new capture event
- **Baseline vs manual:** metadata only

### `context.md`

- **Kind:** qualitative review notes (human/agent authored)
- **Immutable:** append-friendly; do not erase prior evidence
- **Required:** capture/review dates; cited sources for injury/QB/weather claims
- **Regenerate?** Update in place carefully; prefer dated sections
- **Baseline vs manual:** review signals only; must not silently redefine baseline
  probabilities

### `market/<stamp>/market.csv` + `manifest.json`

- **Kind:** generated/captured market baseline input (`weekly_market.v1`)
- **Immutable:** yes (new stamp for new pulls; never overwrite)
- **Required timestamps/hashes:** `snapshot_at_utc`, slate hash, file hashes in
  manifest; per-row moneylines/spreads/totals and `status`
- **Regenerate?** New directory only
- **Baseline vs manual:** this is the preferred odds source for
  `weekly recommend --market ...` and `weekly tiebreaker --market ...`
- **CLI gap:** no `weekly fetch-market` command is committed; directories may still
  exist from prior authorized captures

### `signals/<stamp>/signals.csv` + `manifest.json` (+ optional `raw/`)

- **Kind:** generated review-signal snapshot (`weekly_signals.v1`)
- **Immutable:** yes
- **Required:** `snapshot_at_utc`, slate hash, coverage stats, request params;
  Elo/FPI/SP+/ranks/venue fields
- **Regenerate?** New directory via `weekly fetch-signals`
- **Baseline vs manual:** review aids only unless promoted by held-out evidence
  (`docs/early_season_results.md`, `docs/baseline_results.md`)

### Recommendation run directory

Typical files:

- `recommendations.csv`
- `card.md`
- `run_manifest.json`
- optional `FINALIZED` marker

- **Kind:** generated market baseline
- **Immutable once finalized:** refuse overwrite when `FINALIZED` exists
- **Required:** schema `weekly_recommendations.v1`; `as_of`; input slate hash;
  optional market path in `command_arguments`; output hashes;
  `generation_timestamp` isolated in the manifest
- **Regenerate?** Allowed into a **new** directory for identical or updated
  inputs; do not clobber finalized runs
- **Baseline vs manual:** `baseline_pick` / probabilities are model/market
  baseline. `card.md` must remain labelled as market baseline, not the submitted
  card. Public % appear for comparison only.

### `tiebreaker/tiebreaker.json` + `tiebreaker.md`

- **Kind:** generated baseline for the designated total
- **Immutable for a given run directory:** treat as a versioned output
- **Required:** schema `weekly_tiebreaker.v1`; `as_of`; market/slate hashes;
  `consensus_market_total`; `recommended_integer_total`; rounding rule;
  game identity
- **Regenerate?** New run/directory when market refreshes
- **Baseline vs manual:** quantitative baseline; final entered total may differ
  only with recorded authorization

### `final_picks.csv`

- **Kind:** final human decision table (example columns from Week 1:
  `display_order`, teams, `pick`, `market_win_probability`, `manual_override`,
  `review_note`)
- **Immutable after submission recording:** do not silently edit; version or
  append change logs for authorized revisions
- **Required:** one row per slate game; override flag + reason when departing
  from baseline
- **Regenerate?** Only under explicit authorization
- **Baseline vs manual:** `manual_override=false` means accepted baseline;
  `true` requires evidence in `review_note` / context
- **CLI gap:** not emitted by current CLI

### `final_card.md`

- **Kind:** final human decision narrative for entry
- **Immutable after submission recording:** same rules as `final_picks.csv`
- **Required:** as-of / market snapshot reference; picks in ESPN display order;
  tiebreaker; statement that standard contests use no confidence points
- **Regenerate?** Only with authorization
- **Baseline vs manual:** must distinguish review notes from baseline agreement
- **CLI gap:** not emitted by current CLI

## Proposed artifacts (implementation gaps)

These are **proposed** contracts. Do not pretend CLI support exists.

### `submission.json` (proposed)

- **Kind:** submission record
- **Immutable:** yes after write
- **Required:** `submitted_at_utc`, submitted picks, submitted tiebreaker,
  hashes of `final_picks.csv` / entry confirmation if available, operator
- **Regenerate?** No; corrections are new versioned files
- **Gap:** no `weekly finalize` / submission command

### `results/` grading pack (proposed)

Suggested files: `results.json`, `grade.md` (exact names left to the future grading CLI).

- **Kind:** postgame result
- **Immutable:** yes once graded for a frozen week
- **Required:** final scores, correctness per game, accuracy, baseline vs
  override delta, actual tiebreaker total, absolute tiebreaker error,
  grading timestamp
- **Regenerate?** Only if scoring inputs were wrong; preserve prior grade files
- **Gap:** `pick-prophet weekly grade` is planned in
  `docs/implementation_plan.md` but not implemented

### `manual_adjustments.csv` (proposed / planned)

Plan calls for explicit override audit rows (game ID, original pick, adjusted
pick, reason, author, timestamp). Until implemented, use `final_picks.csv`
override columns plus `context.md`.

## Distinguishing baseline from decisions

| Layer | Examples | May select winners? |
|---|---|---|
| Market baseline | `recommendations.csv`, recommend `card.md`, `tiebreaker.*` | Baseline only |
| Review signals | `signals.csv`, `context.md`, public % on slate | No automatic selection |
| Final decision | `final_picks.csv`, `final_card.md` | Yes, after authorization |
| Submission proof | proposed `submission.json` | Records what was entered |
| Grade | proposed `results/` | Evaluates frozen decisions |

Never rewrite baseline files to match an override. Record the override beside
the preserved baseline.
