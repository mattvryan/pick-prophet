# Pick Prophet execution plan

Last updated: 2026-09-04

This document is the shared implementation and research queue for Cursor, Codex,
and human contributors. The immediate objective is to produce a defensible 2026
weekly card before this weekend's first Pick'em lock. Historical research remains
important, but it must not prevent a transparent market-based MVP from shipping.

## Definition of success

### This weekend

Given an exact ESPN slate, generate a checked and timestamped card containing:

- selected winner for every game;
- market-derived win probability when a two-way moneyline is available;
- confidence rank with no duplicates when the contest uses confidence points;
- market disagreement and upset flags;
- missing-data warnings;
- separate, recorded manual adjustments; and
- enough provenance to reproduce the card after the games.

The initial card is explicitly a **market baseline**, not a trained AI model.
Shipping a labelled baseline is more rigorous than fitting a model to one season
or inventing weights under deadline pressure.

### Research release

Demonstrate through season-level walk-forward tests whether any candidate model
improves held-out log loss or Brier score over a vig-removed market baseline.
Accuracy alone is not sufficient. The exact ESPN slate is the preferred sampling
frame; all-FBS results must be labelled provisional.

## Work streams and priority

There are two parallel work streams:

1. **Weekly operations (P0):** capture the current slate, obtain market data,
   produce and validate this weekend's picks.
2. **Historical research (P1):** build multiple point-in-time seasons, backtest,
   calibrate, and decide whether additional variables merit production use.

P0 takes precedence until the weekly card has been archived. P1 must never change
the current week's card without producing a new version and an audit entry.

## P0: weekend MVP

Complete these tasks in order. A task is complete only when its acceptance checks
pass and its checkbox is updated in this file.

### P0.1 — Environment and credentials

- [x] Create `.venv` and install `.[dev]`.
- [x] Configure `CFBD_API_KEY` locally; never commit the value.
- [x] Run `pytest` and the CLI help command.

Acceptance:

```bash
pytest
pick-prophet --help
```

Both commands exit successfully. If CFBD access cannot be obtained immediately,
continue with manual odds import rather than blocking the card.

### P0.2 — Capture the exact ESPN slate

- [x] Create `weekly/2026-WNN/slate.csv` from the contest page.
- [x] Record ESPN game ID if visible, teams, kickoff, display order, lock time,
  confidence-mode status, source URL, and `captured_at_utc`.
- [x] Record screenshot filenames and hashes in a capture manifest.
- [x] Match every row to a CFBD game ID; unresolved matches remain explicit.

Implement `pick-prophet weekly validate-slate PATH`. It must reject duplicate game
IDs, duplicate display positions, missing teams, malformed timestamps, and games
whose kickoff precedes capture. It must warn, not guess, on unmatched IDs.

- [x] Implement `weekly validate-slate` with row-specific errors/warnings and
  nonzero exit on failure.

Acceptance: row count equals the visible ESPN slate, a second person or a second
independent capture verifies the teams/order, and validation produces zero errors.

### P0.3 — Current market snapshot

- [ ] Add current-season/week ingestion rather than downloading all 20 future
  weeks for a weekly run.
- [ ] Store raw provider lines and retrieval timestamps without overwriting them.
- [ ] Join odds by stable game ID.
- [ ] Add a documented manual import contract for games missing from CFBD.

The consensus line is the median across available books. The two-way moneyline
probability is normalized to remove vig. Do not convert a missing moneyline to a
fabricated probability. Spread may still determine the market favorite and sort
order, but output must say that calibrated probability is unavailable.

Acceptance: every slate game has either a market record or a visible `missing`
reason; home-team spread sign is verified on at least three games against the raw
source; snapshot timestamp precedes lock.

### P0.4 — Weekly recommendation engine

Implement `src/pick_prophet/weekly/recommend.py` and:

```bash
pick-prophet weekly recommend \
  --slate weekly/2026-WNN/slate.csv \
  --as-of 2026-09-05T16:00:00Z
```

- [x] Implement market-baseline `weekly recommend` for standard contests (no
  confidence points), writing `recommendations.csv`, `card.md`, and
  `run_manifest.json`. Week 1 production card not published in this step.

Rules for version 0:

1. Pick the side with market probability greater than 0.5.
2. For confidence contests only, rank confidence by distance from 0.5. If
   probabilities are unavailable, use absolute consensus spread only as a clearly
   labelled fallback.
3. Break ties deterministically by ESPN display order, then game ID.
4. For confidence contests only, assign points `1..N`, with `N` on the strongest
   pick. Standard contests leave confidence fields null.
5. Set `upset_candidate=true` only when a later model/manual selection chooses
   the market underdog. Market-baseline output has no disagreement by definition.
6. Preserve the original model selection and probability when a manual override
   is applied.

Output both `recommendations.csv` and `card.md`, including source snapshot IDs,
generation time, missingness, and warnings.

Acceptance: one row per slate game; winner is always one of the two teams;
confidence values are null for the current standard league; rerunning identical
inputs is byte-stable except for an explicitly separated run manifest.

### P0.5 — Manual review and final lock snapshot

- [ ] Add `manual_adjustments.csv` with game ID, original pick, adjusted pick,
  reason, author, and timestamp.
- [ ] Review injury, suspension, weather, venue, and late-QB news only for changes
  not plausibly captured by the odds snapshot.
- [x] Capture an initial structured ratings/rankings/venue snapshot and official
  game-week context review; weather and final availability refresh remain pending.
- [ ] Refresh odds as close to contest lock as practical.
- [ ] Generate a final versioned card and enter it in ESPN.
- [x] Save an entry-confirmation capture and checksum the final inputs/outputs
  via `pick-prophet weekly record-submission` (writes immutable
  `submission.json`).

Manual judgment must not edit model probabilities. It creates a second
`final_pick` column and an audit record. Confidence can be overridden, but the
original rank must remain visible.

### P0.6 — Grade the week

Implement `pick-prophet weekly grade` after results are final. Save straight-up
accuracy, confidence points earned/possible, Brier score and log loss where
probabilities exist, market baseline result, manual-adjustment delta, and closing
line value when comparable timestamps are available.

- [x] Implement `weekly fetch-results` and `weekly grade` for completed slates.
  Closing-line value comparison remains future work when timed CLV snapshots exist.

Never train on the current week until results are final and the raw weekly
directory has been frozen.

## P1: historical dataset

### P1.1 — Harden ingestion

- [x] Add retries with bounded exponential backoff for retryable HTTP responses.
- [x] Add endpoint-schema validation and actionable errors.
- [x] Support targeted seasons/weeks and resume incomplete snapshots.
- [x] Record request parameters, API version if exposed, row counts, hashes, and
  retrieval time in the manifest.
- [x] Add fixture-based contract tests for every endpoint.

Never silently adapt to a provider schema change. Preserve the bad raw response,
fail the build, and update the adapter plus fixture deliberately.

### P1.2 — Build the modeling window

- [x] Ingest 2017–2025, starting with 2025 as the end-to-end validation season.
- [x] Produce one canonical CSV table and quality report per season.
- [x] Validate game counts, duplicate IDs, completed outcomes, odds coverage,
  rating coverage, team identities, and neutral-site flags.
- [x] Create a cross-season coverage report before fitting any model.

The date range may be widened after coverage is known. A season with poor feature
coverage can still serve the Vegas baseline but must not be silently dropped from
comparative results.

### P1.3 — Recover the ESPN sampling frame

- [x] Inventory personal exports, screenshots, emails, browser captures, and pool
  records for contest slates and pick percentages.
- [x] Check dated web archives and document successes/failures.
- [x] Build a transcription/import tool with source and capture timestamps.
- [x] Require two-source or two-person verification for manually transcribed rows.
- [x] Report all-FBS and confirmed-Pick'em results separately.

Do not infer ESPN membership from rankings, TV network, or matchup prominence.

Notes (2026-09-04): tooling and inventory checklist land first
(`docs/pickem_inventory.md`, `pick-prophet pickem …`). No historical ESPN
archives were found in-repo; the results table remains empty until real
artifacts are transcribed. All-FBS vs confirmed-Pick'em labeling stays separate
in analysis.

### P1.4 — Point-in-time team context

Implement and test in this order:

- [x] entering wins/losses and previous-game result from shifted game history;
- [x] conference and neutral-site status;
- [x] latest pre-kickoff AP, Coaches, and CFP ranks;
- [x] FPI/SP+ left null historically; Elo week *w-1* joined; Massey/Sagarin deferred;
- [x] strength of schedule using only games known before kickoff;
- [ ] head coach, tenure, and first-year flag;
- [ ] returning-QB flag with a written definition and season-specific source;
- [ ] rivalry flag from a versioned mapping, not text matching.

Every derived feature needs a unit test showing that changing a future game's
result cannot alter an earlier row.

Notes (2026-09-04): Elo (week *w-1*) plus conference/neutral/ranks ship.
Entering W-L, previous result, and pre-kickoff SOS ship with leakage tests.
Season-level FPI/SP+ remain unjoined. Massey/Sagarin, returning QB, rivalry,
and coach tenure stay deferred (licensing / missing adapters / undefined
sources)—do not fabricate them for P2 all-FBS provisional labeling.

## P2: modeling and evaluation

The branch-by-branch implementation sequence for this phase is maintained in
`docs/modeling_implementation_roadmap.md`.

### P2.1 — Freeze the evaluation protocol

- [x] Choose first training and test seasons after reviewing coverage.
- [x] Use expanding-window season folds; prohibit random splits.
- [x] Fit preprocessing independently inside every training fold.
- [x] Measure accuracy, log loss, Brier score, calibration, and coverage.
- [x] Bootstrap uncertainty by week.
- [x] Save predictions for every model/fold, not only aggregate scores.

Notes (2026-09-04): protocol **1.0.0** freezes test seasons `2018–2025`
(train on prior seasons only). `2025` is the latest in-loop OOT fold;
prospective holdout is `2026_weekly_shadow`. Use
`pick-prophet evaluate --protocol 1.0.0`.

### P2.2 — Baselines

Evaluate before building a full model:

- favorite by closing spread;
- vig-removed closing moneyline probability;
- FPI only;
- SP+ only;
- public picks only, where available;
- expert consensus only, where available.

- [x] Establish direct spread/moneyline and walk-forward spread/Elo baselines;
  FPI, SP+, public picks, and experts remain blocked by point-in-time archives.

Rank-based sources need an explicit unranked representation and missing indicator;
never replace unranked with rank 26 without testing that modeling choice.

### P2.3 — Incremental-value experiments

For each signal `X`, compare `Vegas` against `Vegas + X` on identical held-out
rows. Report the paired change in log loss/Brier score and its uncertainty. Run
predeclared slices for early season, neutral site, rivalry, home/away, and market
favorite strength. Treat slice findings as exploratory unless sample sizes and
multiple-comparison controls are adequate.

Promotion rule: a signal enters the production model only if it improves proper
scoring rules across multiple held-out seasons, remains reasonably calibrated,
has useful coverage, and has an operationally available pre-lock value.

### P2.4 — Model progression

1. Regularized logistic regression with Vegas only.
2. Regularized logistic regression with independently useful signals.
3. Gradient boosting using the same folds and rows.
4. Probability calibration fitted only inside training data.

Prefer the simplest model whose held-out performance is statistically and
operationally competitive. Save a model card listing training window, features,
missing-value behavior, calibration, limitations, and artifact hash.

## P3: production weekly workflow

- [ ] `weekly capture`: create the dated directory and slate contract.
- [ ] `weekly fetch`: snapshot market and approved feature sources.
- [ ] `weekly recommend`: emit immutable model recommendations.
- [ ] `weekly review`: apply separately logged qualitative changes.
- [ ] `weekly finalize`: validate and checksum the entered card.
- [x] `weekly record-submission`: immutable ESPN entry confirmation record.
- [x] `weekly fetch-results` / `weekly grade`: capture scores and grade the card.
- [ ] `weekly report`: append cumulative market/model/manual comparisons.

The production model must refuse to run when required columns, feature versions,
or model schema differ. It should degrade to the market baseline when optional
signals are missing, with a prominent warning.

## Repository and implementation rules for Cursor

1. Read this plan, `docs/schema.md`, `docs/methodology.md`, and
   `docs/data_sources.md` before editing.
2. Take the first unchecked, unblocked task in priority order unless assigned a
   specific task.
3. Keep external I/O in `ingest/`, pure transformations in `features/`, fitting
   in `models/`, scoring in `evaluation/`, and orchestration in `weekly/`/CLI.
4. Put reusable logic in `src/`; notebooks may call it but may not be its only
   implementation.
5. Add or update tests in the same change. Prefer tiny committed fixtures to live
   API calls in tests.
6. Never commit credentials, copyrighted bulk exports, mutable API responses, or
   personally identifiable pool data.
7. Do not overwrite raw snapshots or finalized weekly cards.
8. Preserve nulls and emit coverage reports; do not use truthy/falsy defaults for
   numeric sports data because zero is meaningful.
9. Use stable IDs for joins. Any name-based fallback must emit an audit table.
10. Update the relevant checkbox and add a dated entry to the decision log after
    acceptance checks pass.

## Pull request / handoff checklist

Every implementation handoff should state:

- task ID and scope;
- files changed;
- commands run and results;
- new data sources and their timing semantics;
- known missing data;
- leakage risks considered;
- whether outputs are provisional, baseline, experimental, or production-ready;
- the next unblocked task.

## Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-09-04 | Ship a market-baseline weekly card before a trained model | The deadline precedes completion of a credible multi-season backtest |
| 2026-09-04 | Use 2017–2025 as the initial research window | It provides multiple walk-forward folds while keeping source coverage plausibly modern; retain only after coverage audit |
| 2026-09-04 | Keep all-FBS and confirmed ESPN-slate evaluation separate | ESPN's selection process changes the game distribution and may bias results |
| 2026-09-04 | Preserve manual picks separately from model output | Required to measure whether qualitative intervention helps or hurts |
| 2026-09-04 | Treat the screenshot's left team as away and lock times as America/Denver | All ten pairings are consistent with that orientation; retain as an explicit assumption pending user confirmation |
| 2026-09-04 | Do not blend pregame Elo into the Week 1 market baseline | On identical Week 1 rows across eight walk-forward folds, spread + Elo had worse log loss and Brier score than spread alone |
| 2026-09-04 | Ship weekly validate/recommend machinery before publishing the Week 1 card | Lets the market baseline be tested on synthetic fixtures without locking in this weekend's selections early |
| 2026-09-04 | Harden CFBD ingest before P2 (retries, schema, resume, fixtures) | Provider drift must fail loudly; CI must not call the live API |
| 2026-09-04 | Require regenerable cross-season coverage gates before modeling | Seasons with thin coverage stay labelled, never silently dropped |
| 2026-09-04 | Pickem recovery is tooling-first until real archives exist | No in-repo historical ESPN slates; do not invent membership |
| 2026-09-04 | Ship entering W-L / previous result / SOS; defer FPI archives, Massey/Sagarin, QB, rivalry, coaches | Enough leakage-safe history for provisional all-FBS P2; blocked sources stay explicit |
| 2026-09-04 | Freeze evaluation protocol 1.0.0 with test seasons 2018–2025; 2025 latest OOT; 2026 weekly shadow prospective holdout | 2025 already inspected so it cannot be pristine; limit further adaptation to the historical window |
| 2026-09-04 | Extend coverage auditor with week tables, structural vs join missingness, and usable-window recommendations | P1.2 gates were thin; M02 must label FPI/SP+ as structurally blocked without dropping seasons |

## Immediate human inputs needed

- A local CFBD API key, or permission to proceed with manual odds input.
- Any historical screenshots, exports, or emails that can establish prior ESPN
  slate membership and public-pick percentages.
