# Modeling implementation roadmap

Last updated: 2026-09-04

This roadmap starts after the Week 1 market-baseline workflow. Each segment is a
separate branch and pull request. The objective is a reproducible point-in-time
model that proves incremental value beyond the betting market—not maximum model
complexity.

## Program acceptance criteria

A model is eligible for weekly shadow use only when:

1. Every feature was available before kickoff and has documented timing semantics.
2. Primary validation uses expanding season-level walk-forward folds.
3. Market-only and candidate models are compared on identical held-out game IDs.
4. Preprocessing, imputation, tuning, and calibration fit only on training data.
5. Reports include accuracy, log loss, Brier score, calibration, coverage, and
   fold-level paired deltas. Accuracy alone cannot promote a model.
6. Row-level predictions are saved with game ID, fold, model, target, and inputs.
7. All-FBS and verified ESPN Pick'em sampling frames remain separate.
8. Missingness and excluded-row reasons remain visible.
9. No candidate replaces the production market baseline until it clears the
   promotion gates below and receives human approval.

## Branch and PR rules

- Start each branch from updated `main` after its dependencies merge.
- One PR owns one contract or capability; do not bundle adjacent stages.
- Suggested names are descriptive, not mandatory.
- Commit small deterministic fixtures, not credentials or mutable/bulk raw data.
- Every PR updates relevant docs and includes tests and acceptance evidence.
- If a source fails timing, licensing, or reproducibility review, document that
  outcome and leave downstream code source-agnostic. Never fabricate a substitute.

## Dependency map

```text
M01 protocol -> M02 audit -> M03 ingestion -> M04 market history
                     |              |
                     |              +---------> M06 rating archives
                     +-> M05 ESPN sampling frame

M01 + M02 + M04 (+ available M05/M06) -> M07 feature matrix
M07 -> M08 residual logistic -> M09 inference/calibration -> M10 ablation
M10 -> M11 boosted challenger -> M12 registry/promotion -> M13 shadow mode
```

M05 and M06 may proceed in parallel after their dependencies. M08 may proceed
without unavailable rating sources; omissions must be explicit.

## M01 — Freeze the evaluation protocol

**Status:** implemented (protocol 1.0.0)
**Branch:** `modeling/m01-evaluation-protocol`
**Dependencies:** none

Purpose: make statistical rules executable before adding features.

Scope:

- [x] Add versioned configuration for training/test seasons, expanding folds,
  metrics, random seeds, and required slices.
- [x] Required slices: Week 1, Weeks 1–3, Week 4+, neutral site,
  favorite-strength bands, and sampling frame.
- [x] Centralize fold construction and paired-row selection in `evaluation/`.
- [x] Define stable row-level prediction and summary schemas.
- [x] Refactor existing baseline and early-season analysis onto those contracts
  without changing expected results beyond documented tolerance.
- [x] Document that tuning and calibration must be nested within training folds.

Tests and acceptance:

- [x] Every training season precedes its test season.
- [x] Mutating a future outcome cannot alter an earlier fold.
- [x] Paired comparisons reject unequal test game-ID sets.
- [x] Repeated runs produce identical folds and predictions.
- [x] One command regenerates existing reports with protocol/schema versions.

Excludes new sources, features, models, and production changes.

## M02 — Cross-season coverage and quality audit

**Branch:** `modeling/m02-coverage-audit`
**Dependencies:** M01

Scope:

- Audit 2017–2025 by season and week: games, outcomes, duplicate/missing IDs,
  home/away, neutral sites, odds, providers/timestamps, ratings, rankings, and
  join failures.
- Distinguish structural missingness from adapter or join failure.
- Emit machine-readable CSV/JSON and `docs/data_coverage_report.md`.
- Define programmatic pass/warn/fail gates for later builds.
- Recommend usable evaluation windows without silently changing them.

Tests and acceptance:

- Fixtures cover duplicates, invalid outcomes/odds, zero ratings, missing weeks,
  and failed identity joins.
- Counts reconcile to canonical inputs; no silent row removal occurs.
- The report identifies usable seasons for each source.

Excludes imputation, feature engineering, and fitting.

## M03 — Harden historical ingestion

**Branch:** `data/m03-ingestion-hardening`
**Dependencies:** M02

Scope:

- Add targeted season/week requests and resumable immutable snapshots.
- Add bounded exponential backoff for retryable failures only.
- Validate provider schemas before canonical transformation.
- Record parameters, retrieval time, row counts, hashes, adapter version, and
  errors in manifests.
- Preserve bad responses and fail with actionable schema-drift errors.
- Prefer stable IDs; emit an audit table for every name-based fallback.
- Keep automated tests fixture-only; document live smoke tests separately.

Tests and acceptance:

- Test retryable/permanent failures, resume, schema drift, and deterministic
  manifests.
- A targeted week capture does not request future weeks.
- Re-running a completed snapshot cannot overwrite it.
- Existing 2017–2025 snapshots still build.

## M04 — Historical market contract and market-logit baseline

**Branch:** `data/m04-market-history`
**Dependencies:** M03

Scope:

- Define timestamped provider and consensus schemas.
- Preserve opening, latest-prelock, and closing observations when available;
  document the operational meaning of each.
- Aggregate moneylines through implied probabilities, never arithmetic American
  odds averages.
- Calculate two-way vig-free probabilities and bounded market logits.
- Retain spread/total; never fabricate primary moneyline probabilities from them.
- Add timestamped line-movement candidates and provider/season/week coverage.

Tests and acceptance:

- Cover American-odds discontinuity, vig removal, missing sides, aggregation,
  point-in-time snapshot selection, and rejection of post-kick observations.
- Regenerate market-only row predictions under M01 with reconciled coverage.
- Never infer opening/closing order without timestamps.

## M05 — Verified ESPN Pick'em sampling-frame registry

**Branch:** `data/m05-espn-slate-registry`
**Dependencies:** M02; parallel with M03–M04

Scope:

- Define a source-provenanced historical slate import contract.
- Support verified transcription of screenshots/exports with source hashes.
- Store contest season/week, display order, game ID, public percentage and its
  capture time, tiebreaker identity, and verification status when available.
- Join by stable ID and isolate fallback matches for review.
- Add explicit `all_fbs` and `verified_espn_pickem` sampling-frame labels.
- Inventory available evidence and report unrecoverable weeks.

Tests and acceptance:

- Reject duplicate positions/games and ambiguous matches.
- Never infer ESPN membership from ranking, TV, or prominence.
- Every evaluation output labels its sampling frame.

Do not scrape sources in violation of their terms.

## M06 — Point-in-time rating adapters

**Branch:** `data/m06-pit-ratings`
**Dependencies:** M03

First produce a feasibility memo for Elo, FPI, and SP+ covering weekly historical
availability, publication semantics, licensing, identifiers, and coverage.

Implement only sources that pass review:

- Preserve effective/publication time separately from retrieval time.
- Select the latest observation strictly before kickoff.
- Represent missing and unranked values explicitly.
- Prohibit current/end-of-season ratings in historical pregame rows.

Tests and acceptance:

- Test kickoff boundaries, future-week exclusion, zero/negative ratings, and
  deterministic duplicate resolution.
- Publish source coverage and a sampled leakage audit.

Stop condition: if historical FPI or SP+ cannot be legally and reproducibly
obtained, finish the memo/interface and omit that source. Do not substitute.

## M07 — Leakage-safe modeling feature matrix

**Branch:** `modeling/m07-feature-matrix`
**Dependencies:** M01, M02, M04; include merged M05/M06 outputs when available

Build one versioned row per game with target and verified pregame features:

- market probability/logit, spread, total, and valid line movement;
- approved pregame ratings and rating-versus-market disagreements;
- home/neutral status, conference, season/week, and early-season interactions;
- entering record, previous result, and rest derived by chronological shifts;
- feature timestamps or snapshot IDs sufficient for audit.

Keep transformation/scaling out of this raw matrix. Emit missingness and
excluded-row reason reports, schema version, and input-manifest hashes.

Tests and acceptance:

- Future-result mutation cannot alter earlier features.
- Test chronological shifts, stable-ID joins, neutral sites, schema/order, and
  deterministic rebuilds.
- One command rebuilds the matrix; every column is defined in `docs/schema.md`.
- Model-specific complete-case filtering does not occur in the shared build.

Defer coaching, QB continuity, returning production, rivalry, travel, and weather
until each has its own approved point-in-time source contract.

## M08 — Market-residual logistic model

**Branch:** `modeling/m08-market-residual-logit`
**Dependencies:** M07

Implement the interpretable candidate:

```text
logit(P(win)) = logit(P_market) + adjustment(features)
```

Use a tested fixed-offset implementation or its mathematically equivalent
residual formulation; simply including market probability as an ordinary feature
does not satisfy this contract.

Scope:

- Compare market only; market + each rating disagreement; market + approved
  combined ratings; and market + basic temporal/site context.
- Fit imputation, missing indicators, scaling, regularization, and selection
  within each fold.
- Save coefficients, offset behavior, feature list, model hash, and row-level
  probability adjustment.
- Use probability clipping only for numerical scoring.

Tests and acceptance:

- Zero adjustment reproduces the market baseline.
- Public percentages cannot affect predictions.
- Preprocessing cannot see held-out rows.
- Serialization round-trips without drift.
- All variants run under M01 on identical paired rows.

Excludes boosting, production promotion, and qualitative news features.

## M09 — Inference and calibration diagnostics

**Branch:** `modeling/m09-inference-calibration`
**Dependencies:** M08

Scope:

- Add paired metric deltas by fold and aggregate.
- Bootstrap uncertainty using weeks or seasons as documented clusters.
- Add reliability tables/plots and calibration intercept/slope.
- Analyze candidate adjustments and winner flips by magnitude.
- Label exploratory slices and use multiple-comparison controls for confirmatory
  claims.

Tests and acceptance:

- Deterministic resampling with configured seed.
- Known perfect/constant/adversarial fixtures yield expected metrics.
- Unequal paired game IDs fail.
- Reports show uncertainty, fold consistency, coverage, and denominators.

## M10 — Feature ablation and robustness report

**Branch:** `modeling/m10-ablation-robustness`
**Dependencies:** M08–M09

Scope:

- Run predeclared single-feature additions and leave-family-out ablations.
- Report early season, neutral site, location, favorite strength, conference, and
  verified-ESPN slices with sample sizes.
- Check coefficient stability, missingness dependence, season sensitivity, and
  sensitivity to anomalous seasons.
- Produce `docs/incremental_value_report.md` with decisions per feature family:
  promote, retain as review-only, or reject.

Acceptance: every comparison is paired and exposes coverage loss; no feature is
approved from one favorable season or exploratory slice.

## M11 — Gradient-boosting challenger

**Branch:** `modeling/m11-boosted-challenger`
**Dependencies:** M10

Scope:

- Implement one justified boosting family using the approved M10 feature set.
- Use the same folds and rows as market and logistic benchmarks.
- Tune a small predeclared search space only within training seasons.
- Compare raw and training-only calibrated probabilities.
- Report feature importance with explicit non-causal caveats.

Tests and acceptance:

- Held-out seasons cannot influence tuning or calibration.
- Seeds reproduce predictions and missing-value behavior is tested.
- Reject added complexity unless proper-score gains are stable and meaningful.

## M12 — Model registry and promotion gate

**Branch:** `modeling/m12-model-registry`
**Dependencies:** M09–M11

Scope:

- Define candidate, shadow, approved, and retired lifecycle states.
- Save immutable artifacts with model/schema hashes, training window, protocol,
  feature sources, preprocessing/calibration, metrics, coverage, and limitations.
- Implement a promotion evaluator requiring:
  - held-out log-loss and Brier improvement;
  - no material calibration regression;
  - improvement across multiple seasons;
  - adequate coverage and pre-lock availability;
  - no unresolved leakage finding.
- Require human approval; the evaluator must not self-promote.

Tests and acceptance:

- Reject tampered artifacts and feature/schema incompatibility.
- Failed gates cannot create an approved model.
- If nothing passes, retaining the market baseline is a valid successful result.

## M13 — Weekly shadow-mode integration

**Branch:** `production/m13-shadow-model`
**Dependencies:** M12

Scope:

- Add a weekly shadow command/mode that loads only compatible registered models.
- Enforce training/serving feature parity and point-in-time joins.
- Emit market and shadow picks/probabilities, adjustment, disagreement, warnings,
  and all model/input hashes without altering the market card.
- Fall back visibly to market when optional features are unavailable.
- Extend grading to compare market, shadow, and authorized manual decisions.
- Never silently change final or submitted picks.

Tests and acceptance:

- Test parity, incompatible schemas, missing-signal fallback, and immutable final
  artifacts.
- Process at least one slate end to end with output labelled experimental.

## Deferred feature-family PRs

Each requires an approved source/timing contract and a later M10-style ablation:

| Branch | Feature family | Required evidence |
|---|---|---|
| `features/coaching-context` | Coach identity/tenure/first year | Dated staff history and stable IDs |
| `features/qb-continuity` | Returning or changed starter | Written definition and dated sources |
| `features/returning-production` | Roster production | Licensed preseason snapshots |
| `features/rivalry-registry` | Rivalry flag | Versioned curated mapping, not text heuristics |
| `features/travel-rest` | Rest and travel | Schedules and reproducible venue coordinates |
| `features/weather-history` | Kickoff weather | Archived forecast/observation semantics |

Qualitative injuries and breaking news stay outside training until a consistently
timed historical dataset exists.

## Cursor execution protocol

For every PR, Cursor must:

1. Read this roadmap, `docs/schema.md`, `docs/methodology.md`, and current code.
2. Confirm dependencies are merged and restate scope, exclusions, and acceptance.
3. Implement reusable logic in `src/pick_prophet/`; notebooks may consume it but
   cannot contain the only implementation.
4. Add deterministic tests in the same PR.
5. Run:

   ```bash
   ruff format src tests
   ruff check src tests
   pytest -q
   python -m compileall -q src tests
   git diff --check
   ```

6. Run the PR-specific acceptance workflow and inspect generated artifacts.
7. Update this roadmap only for verified completion or a documented blocker.
8. Hand off branch/PR, files and schemas, commands/results, source timing,
   coverage changes, leakage tests, artifacts, limitations, and next PR.

Do not begin the next segment on the same branch. Merge or close the current
scope first so every data and statistical decision remains independently
reviewable.
