# M01 evaluation protocol design

Date: 2026-09-04
Status: draft for review
Roadmap: `docs/modeling_implementation_roadmap.md` § M01
Plan: `docs/implementation_plan.md` § P2.1
Branch (planned): `modeling/m01-evaluation-protocol`

## Problem

Historical baselines (`analyze.py`, `early_season.py`) already walk forward by
season, but fold construction, metrics, prediction schemas, and sampling-frame
labels are duplicated and not versioned. Before adding features or models, the
evaluation contract must be frozen so later work cannot silently adapt to the
2018–2025 window.

## Goals

1. Make statistical rules executable and versioned (`protocol_version`).
2. Centralize expanding-window folds and paired `game_id` selection.
3. Define stable row-level prediction and summary schemas.
4. Refactor existing baselines onto those contracts without meaningful result
   churn.
5. Document nested train-only fitting/calibration and the prospective 2026
   shadow holdout.

## Non-goals (M01)

- New data sources, features, or candidate models
- Production `weekly recommend` changes
- Full nested hyperparameter search implementation (declare and enforce the
  rule; stub “required before promotion”)
- Treating 2025 as a pristine locked holdout

## Decisions already approved

| Decision | Choice |
|---|---|
| Approach | Protocol module + thin wrappers around existing analyzers |
| Test seasons | 2018–2025 expanding window; train on all prior seasons only |
| 2025 role | In-loop fold; also reported as `latest_oot_fold` |
| Prospective holdout | Immutable 2026 weekly shadow predictions (not scored in WF) |
| Adaptation | Freeze protocol/candidate progression now; window/rule changes bump `protocol_version` |

## Fold and holdout contract

1. `protocol_version = "1.0.0"` stamped on every summary and prediction artifact.
2. Research window seasons: `2017–2025`. Test seasons: `2018–2025`. For test
   season *S*, training rows are completed games with `season < S`.
3. No random splits. Fold membership must not depend on wall-clock RNG. A fixed
   seed (`20260904`) is used only for week-clustered bootstrap resampling.
4. Summaries emit `latest_oot_fold: 2025` so the newest in-loop season is
   visible without implying a pristine lockbox.
5. Config records `prospective_holdout = "2026_weekly_shadow"`. Historical
   walk-forward must not score this holdout. Later shadow mode (M13) writes
   immutable predictions against it.
6. Paired model comparisons require identical test `game_id` sets (or an
   explicit unpaired/skipped reason). Unequal sets are rejected for promotion
   metrics.
7. Changing the 2018–2025 window, pairing rules, or metric definitions requires
   a new `protocol_version`, not silent edits.

## Metrics, slices, and uncertainty

**Primary metrics:** accuracy, log loss, Brier, coverage (`n` / eligible), and
calibration (10 equal-width bins on `[0, 1]`: count, mean predicted, mean
outcome). Accuracy alone cannot promote a model.

**Uncertainty:** week-clustered bootstrap on the test fold (resample weeks with
replacement; default `n_boot=500`, `seed=20260904`). For paired comparisons,
report mean delta log-loss/Brier plus percentile interval.

**Required slices** (per test fold, after all-rows score):

- `week_1`
- `weeks_1_3`
- `weeks_4_plus`
- `neutral_site`
- favorite-strength bands from `|spread_home|`: `<3`, `3–7`, `>7`, and
  `missing_spread`
- `sampling_frame`: `all_fbs` always; `verified_espn_pickem` when confirmed
  Pick’em flags exist, otherwise document pickem unavailable

## Artifact schemas

### Predictions (CSV or JSONL)

Required columns:

- `protocol_version`
- `model`
- `fold_id` (e.g. `test_2024`)
- `test_season`
- `game_id`
- `week`
- `y_true`
- `p_home`
- `sampling_frame`

Optional: `run_id`, feature/input hash.

### Summary JSON

- Protocol config snapshot (seasons, seed, bootstrap, holdout metadata)
- Per-fold metrics and per-slice metrics
- Paired deltas vs declared baseline model
- Skipped-fold reasons
- `latest_oot_fold` highlight for 2025
- `prospective_holdout` metadata

## Nested fitting rule

Scaler, imputer, model hyperparameters, and calibration may fit only on
`season < S` for fold *S*. Nested selection, when used, stays inside the
training window. M01 documents this and exposes fold APIs; full nested tuning
can wait for later model PRs but is required before promotion.

## Baseline plug-in

Refactor `src/pick_prophet/evaluation/analyze.py` and `early_season.py` to:

- build folds via the protocol module;
- write predictions/summaries that include `protocol_version`;
- keep the current candidate set (spread / Elo / spread+Elo; FPI/SP+ remain
  skipped with explicit reasons when coverage is empty).

**Tolerance:** same fold seasons and game counts; metric differences within
floating noise (~1e-9 relative) unless a documented pairing fix changes the
comparable set (called out in the PR).

## CLI

One regenerating entry point, e.g.:

```bash
pick-prophet evaluate --input PATH [--protocol 1.0.0] [--output-dir DIR]
```

Reports must be reproducible from protocol config + input CSV alone. Existing
`analyze` / `analyze-early-season` may wrap the same contracts for back-compat.

## Tests and acceptance (from roadmap)

- Every training season precedes its test season.
- Mutating a future outcome cannot alter an earlier fold’s membership or prior
  fold predictions.
- Paired comparisons reject unequal test game-ID sets.
- Repeated runs produce identical folds and predictions (fixed seed).
- One command regenerates reports with protocol/schema versions stamped.

## Implementation sketch

| Piece | Location |
|---|---|
| Frozen config / version | `evaluation/protocol.py` (+ optional `config/evaluation_protocol_v1.toml`) |
| Fold builder + pairing | `evaluation/folds.py` |
| Metrics + calibration + bootstrap | extend `evaluation/metrics.py` |
| Schemas / writers | `evaluation/artifacts.py` |
| CLI | `pick-prophet evaluate` in `cli.py` |
| Docs | update methodology + roadmap M01 checkbox after acceptance |

## Open follow-ups (out of M01)

- M02 deepens coverage gates (partially landed via P1.2; roadmap may mark
  overlap when implementing).
- M05/M08+ populate `verified_espn_pickem` and residual models under this
  protocol without changing fold years silently.
- M13 materializes 2026 weekly shadow as the prospective holdout scorer.
