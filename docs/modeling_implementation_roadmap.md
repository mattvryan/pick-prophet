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

**Status:** implemented (extends P1.2 auditor)
**Branch:** `modeling/m02-coverage-audit`
**Dependencies:** M01

Scope:

- [x] Audit 2017–2025 by season and week: games, outcomes, duplicate/missing IDs,
  home/away, neutral sites, odds, providers/timestamps, ratings, rankings, and
  join failures.
- [x] Distinguish structural missingness from adapter or join failure.
- [x] Emit machine-readable CSV/JSON and `docs/data_coverage_report.md`.
- [x] Define programmatic pass/warn/fail gates for later builds.
- [x] Recommend usable evaluation windows without silently changing them.

Tests and acceptance:

- [x] Fixtures cover duplicates, invalid outcomes/odds, zero ratings, missing weeks,
  and failed identity joins.
- [x] Counts reconcile to canonical inputs; no silent row removal occurs.
- [x] The report identifies usable seasons for each source.

Excludes imputation, feature engineering, and fitting.

Notes: Provider observation timestamps remain unavailable in CFBD historical
lines; provider *counts* are audited. FPI/SP+ are classified
`structural_unjoined` until dated weekly archives exist.

## M03 — Harden historical ingestion

**Status:** implemented (core in P1.1; M03 closes name-join audit + smoke docs)
**Branch:** `data/m03-ingestion-hardening`
**Dependencies:** M02

Scope:

- [x] Add targeted season/week requests and resumable immutable snapshots.
- [x] Add bounded exponential backoff for retryable failures only.
- [x] Validate provider schemas before canonical transformation.
- [x] Record parameters, retrieval time, row counts, hashes, adapter version, and
  errors in manifests.
- [x] Preserve bad responses and fail with actionable schema-drift errors.
- [x] Prefer stable IDs; emit an audit table for every name-based fallback.
- [x] Keep automated tests fixture-only; document live smoke tests separately.

Tests and acceptance:

- [x] Test retryable/permanent failures, resume, schema drift, and deterministic
  manifests.
- [x] A targeted week capture does not request future weeks.
- [x] Re-running a completed snapshot cannot overwrite it.
- [x] Existing 2017–2025 snapshots still build.

Live smoke steps: `docs/cfbd_live_smoke.md`. Name-based poll/Elo joins write
`games_YYYY.name_join_audit.csv` beside the processed table.

## M04 — Historical market contract and market-logit baseline

**Status:** implemented
**Branch:** `data/m04-market-history`
**Dependencies:** M03

Scope:

- [x] Define timestamped provider and consensus schemas.
- [x] Preserve opening, latest-prelock, and closing observations when available;
  document the operational meaning of each.
- [x] Aggregate moneylines through implied probabilities, never arithmetic American
  odds averages.
- [x] Calculate two-way vig-free probabilities and bounded market logits.
- [x] Retain spread/total; never fabricate primary moneyline probabilities from them.
- [x] Add timestamped line-movement candidates and provider/season/week coverage.

Tests and acceptance:

- [x] Cover American-odds discontinuity, vig removal, missing sides, aggregation,
  point-in-time snapshot selection, and rejection of post-kick observations.
- [x] Regenerate market-only row predictions under M01 with reconciled coverage.
- [x] Never infer opening/closing order without timestamps.

Contract doc: `docs/market_contract.md`.

## M05 — Verified ESPN Pick'em sampling-frame registry

**Status:** implemented (tooling; no historical archives ingested yet)
**Branch:** `data/m05-espn-slate-registry`
**Dependencies:** M02; parallel with M03–M04

Scope:

- [x] Define a source-provenanced historical slate import contract.
- [x] Support verified transcription of screenshots/exports with source hashes.
- [x] Store contest season/week, display order, game ID, public percentage and its
  capture time, tiebreaker identity, and verification status when available.
- [x] Join by stable ID and isolate fallback matches for review.
- [x] Add explicit `all_fbs` and `verified_espn_pickem` sampling-frame labels.
- [x] Inventory available evidence and report unrecoverable weeks.

Tests and acceptance:

- [x] Reject duplicate positions/games and ambiguous matches.
- [x] Never infer ESPN membership from ranking, TV, or prominence.
- [x] Every evaluation output labels its sampling frame.

Do not scrape sources in violation of their terms.

Commands: `pick-prophet pickem validate-import|import|from-slate|build-registry|inventory-gaps`.
Inventory: `docs/pickem_inventory.md`.

## M06 — Point-in-time rating adapters

**Status:** M06 feasibility memo complete; adapter implementation deferred.
**Branch:** `data/m06-pit-ratings`
**Dependencies:** M03

First produce a feasibility memo for Elo, FPI, and SP+ covering weekly historical
availability, publication semantics, licensing, identifiers, and coverage.
See `docs/ratings_feasibility.md`.

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

**Status:** implemented (`matrix_schema_version` 1.0.0; ratings deferred in manifest)
**Branch:** `modeling/m07-feature-matrix`
**Dependencies:** M01, M02, M04; M05/M06 outputs included where available

Schema/docs: `docs/matrix_schema.md`. Rebuild:
`pick-prophet matrix --input-dir data/processed --seasons 2017-2025 --output-dir data/processed/matrix`.

Built one versioned row per eligible game with role-separated columns:

- [x] Market probability/logit as baseline inputs; spread/total/movement as model features
- [x] Site/conference, early-season indicators, chronological history + rest
- [x] Pick’em sampling-frame labels in audit columns only
- [x] Manifest ratings inventory defers Elo/FPI/SP+ (no null rating columns)
- [x] Missingness + exclusion reports; deterministic manifest; volatile run envelope
- [x] Hard tests: no deferred rating fields in matrix; M08 surfaces disjoint

Deferred coaching, QB, rivalry, travel, weather, and rating adapters pending
approved PIT contracts / schema bumps.

## M08 — Market-residual logistic model

**Status:** implemented (matrix schema 1.0.0; ratings variants deferred)
**Branch:** `modeling/m08-market-residual-logit`
**Dependencies:** M07

Model card: `docs/market_residual_model.md`.
Rebuild: `pick-prophet fit-residual --matrix … --output-dir data/processed/residual`.

Implemented the interpretable candidate:

```text
logit(P(win)) = logit(P_market) + adjustment(features)
```

- [x] Fixed-offset L-BFGS-B objective (`λ=1.0`); market logit never a free coefficient
- [x] Variants: `market_only`, `site_temporal`, `history`, `market_context`, `combined`
- [x] Fold-nested preprocess (median+missing indicators, scale, drop-one categoricals)
- [x] Canonical shared eligibility; protocol predictions + residual details + JSON bundles
- [x] Tests for offset identity, leakage, prohibited columns, determinism

M08 must import baseline/predictor roles from `matrix_schema` (schema 1.0.0).
Rating-disagreement variants remain conditional on a later approved matrix schema.

Scope completed for 1.0.0:

- Compare market only vs approved site/temporal, history, market-context, and combined adjustments.
- Fixed L2 (`λ=1.0`); no held-out hyperparameter search.
- Save coefficients, offset behavior, feature lists, hashes, row-level adjustments.
- Probability clipping only in residual-detail scoring field.

Excludes boosting, production promotion, qualitative news, and M09 calibration.

## M09 — Inference and calibration diagnostics

**Status:** implemented (diagnostics on raw M08 `p_home`; no calibrated candidate)
**Branch:** `modeling/m09-inference-calibration`
**Dependencies:** M08

Scope:

- [x] Add paired metric deltas by fold and aggregate.
- [x] Bootstrap uncertainty using weeks or seasons as documented clusters.
- [x] Add reliability tables/plots and calibration intercept/slope.
- [x] Analyze candidate adjustments and winner flips by magnitude.
- [x] Label exploratory slices and use multiple-comparison controls for confirmatory
  claims.

Tests and acceptance:

- [x] Deterministic resampling with configured seed.
- [x] Known perfect/constant/adversarial fixtures yield expected metrics.
- [x] Unequal paired game IDs fail.
- [x] Reports show uncertainty, fold consistency, coverage, and denominators.

Notes: Reliability/calibration/flip/adjustment outputs are machine-readable
tables plus Markdown (no required plots). Calibration fit is diagnostic-only;
post-hoc calibrated `p_home` remains a follow-up if M09 shows stable
miscalibration. Cluster key is `(test_season, season_type, week)`.

## M10 — Feature ablation and robustness report

**Status:** complete (evidence `1.0.0` + human dispositions; `no_features_promoted`)
**Branch:** `modeling/m10-ablation-robustness`
**Dependencies:** M08–M09

Scope:

- [x] Run predeclared single-feature additions and leave-family-out ablations.
- [x] Report early season, neutral site, location, favorite strength, conference, and
  verified-ESPN slices with sample sizes.
- [x] Check coefficient stability, missingness dependence, season sensitivity, and
  sensitivity to anomalous seasons.
- [x] Produce `docs/incremental_value_report.md` with decisions per feature family:
  promote, retain as review-only, or reject.

Acceptance: every comparison is paired and exposes coverage loss; no feature is
approved from one favorable season or exploratory slice.

Notes: Human dispositions recorded in `decision_worksheet.csv` and
`approved_feature_set.json` (`status=no_features_promoted`). Season-drop
analysis aggregates existing held-out predictions (not a retrain). Anomalous
season predeclared: 2020. Verified-ESPN `n < 50` → `insufficient`. Downstream
M11 is closed as not-run for this evidence version (market baseline retained).

## M11 — Gradient-boosting challenger

**Status:** M11 not run: M10 promoted no features; market baseline retained.
**Branch:** `modeling/m11-no-challenger-decision` (not-run close-out);
`modeling/m11-boosted-challenger` reserved if a later M10 promote set reopens
training.
**Dependencies:** M10 approved feature set (`promoted_features` non-empty to
train a challenger)
**Decision:** [`docs/boosted_challenger_decision.md`](boosted_challenger_decision.md)
**Artifact:** [`docs/modeling_artifacts/m11/1.0.0/decision.json`](modeling_artifacts/m11/1.0.0/decision.json)

Scope (deferred until a promoted feature set exists):

- Implement one justified boosting family using the approved M10 feature set.
- Use the same folds and rows as market and logistic benchmarks.
- Tune a small predeclared search space only within training seasons.
- Compare raw and training-only calibrated probabilities.
- Report feature importance with explicit non-causal caveats.

Close-out (this evidence version):

- [x] Validate M10 `approved_feature_set.json` hash before accepting the M11
  decision.
- [x] Record `status=not_run_no_promoted_features`, `challenger_trained=false`,
  baseline retained = `market_only`.
- [x] Document that skipping M11 is an evidence-driven successful outcome.
- [x] Keep future runs fail-closed until at least one feature is explicitly
  promoted; `review_only` / rejected features remain ineligible.

Tests and acceptance:

- Decision artifact references the exact M10 approved-feature-set SHA-256.
- No model bundle or prediction artifact is created for this not-run close-out.
- Held-out seasons cannot influence tuning or calibration (when training is
  later reopened).
- Seeds reproduce predictions and missing-value behavior is tested (when
  reopened).
- Reject added complexity unless proper-score gains are stable and meaningful.

## M12 — Model registry and promotion gate

**Status:** complete (v1 pack: approved `market_only` only; no ML challengers)
**Branch:** `modeling/m12-model-registry`
**Dependencies:** M09–M11
**Docs:** [`docs/model_registry.md`](model_registry.md)
**Artifacts:** [`docs/modeling_artifacts/m12/1.0.0/`](modeling_artifacts/m12/1.0.0/)

Scope:

- [x] Define candidate, shadow, approved, and retired lifecycle states.
- [x] Save immutable artifacts with model/schema hashes, training window, protocol,
  feature sources, preprocessing/calibration, metrics, coverage, and limitations.
- [x] Implement a promotion evaluator requiring:
  - held-out log-loss and Brier improvement;
  - no material calibration regression;
  - improvement across multiple seasons;
  - adequate coverage and pre-lock availability;
  - no unresolved leakage finding;
  - promoted-features-only vs hash-validated M10 set;
  - human approval after automated eligibility.
- [x] Require human approval; the evaluator must not self-promote.
- [x] Bootstrap-approve `market_only` with explicit governance rationale; retain
  market baseline with no challenger as a valid successful outcome.

Tests and acceptance:

- [x] Reject tampered artifacts and feature/schema incompatibility.
- [x] Failed gates cannot create an approved model.
- [x] If nothing passes, retaining the market baseline is a valid successful result.

## M13 — Weekly shadow-mode integration

**Status:** complete (experimental shadow plumbing; live outcome `no_ml_shadow`)
**Branch:** `production/m13-shadow-model`
**Dependencies:** M12
**Docs:** [`docs/weekly_shadow.md`](weekly_shadow.md)

Scope:

- [x] Add a weekly shadow command/mode that loads only compatible registered models.
- [x] Enforce training/serving feature parity and point-in-time joins (PIT audit +
  residual serving contract; boosted interface fail-closed until implemented).
- [x] Emit market and shadow picks/probabilities, disagreement, warnings, and
  model/input hashes without altering the market card.
- [x] Fall back visibly via explicit `no_ml_shadow` when no ML tip exists (null ML
  columns; never silent market substitution for an unavailable ML model).
- [x] Extend grading to compare market, shadow, and authorized manual decisions.
- [x] Never silently change final or submitted picks.

Tests and acceptance:

- [x] Test parity, incompatible schemas, missing-signal/ineligible tips, and
  immutable final artifacts.
- [x] Process at least one slate end to end with output labelled experimental.

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
