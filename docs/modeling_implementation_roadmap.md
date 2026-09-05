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

Post-M13 research cycle:

M14 evidence plan -> M15 ESPN frame + M16 market depth + M17 ratings
                                      + M18 team form + M19 personnel context
M15–M19 approved outputs -> M20 matrix/evaluation -> M21 challenger/promotion
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

## Post-M13 research cycle — earning improvement beyond the market

M01–M13 produced a safe system and an evidence-based decision to retain the
market baseline. The next cycle is not permission to search repeatedly until a
feature appears favorable. Its purpose is to improve the historical evidence,
add independently plausible point-in-time signals, and make one predeclared
attempt to beat the same market baseline.

The 2026 weekly predictions and outcomes are a prospective, locked evaluation
stream. Do not use them to select features, thresholds, hyperparameters, or data
sources during this cycle. Record them through the normal weekly workflow and
reserve their eventual use for a later prospective assessment.

### M14 — Evidence-gap analysis and research protocol 2.0

**Status:** implemented (protocol 2.0.0 frozen; no model fit)
**Suggested branch:** `research/m14-evidence-plan`
**Dependencies:** M13

Purpose: decide what evidence would materially improve the chance of detecting
incremental value before paying for data or expanding model complexity.

Scope:

- Audit why M10 promoted nothing: sample size, feature coverage, effect-size
  uncertainty, market timestamp quality, sampling-frame mismatch, collinearity,
  and season instability.
- Compare the all-FBS training population with the verified ESPN Pick'em
  population without treating an exploratory frame difference as confirmation.
- Run power/minimum-detectable-effect analysis for paired log-loss and Brier
  deltas using week/season dependence.
- Rank candidate source families by independent pregame rationale, PIT and
  licensing feasibility, expected coverage, cost, and testable sample size.
- Freeze protocol `2.0.0`: development seasons, untouched evaluation seasons,
  folds, primary metrics, uncertainty method, multiplicity policy, missingness
  rules, source-family hypotheses, and promotion thresholds.
- Create a machine-readable experiment ledger. Every later analysis must cite a
  predeclared hypothesis or be labelled exploratory and ineligible for immediate
  promotion.

Acceptance:

- The memo can recommend stopping or delaying a source; more data/features are
  not automatically better.
- No candidate is fit and no outcome-dependent source choice is made in M14.
- Protocol and experiment-ledger hashes are recorded before M15–M19 results are
  evaluated.

Artifacts: `docs/modeling_artifacts/m14/2.0.0/`. Protocol:
`docs/research_protocol_2.md`. Experiment ledger:
`docs/experiment_ledger_2.json`.

### M15 — Expand the verified ESPN Pick'em history

**Status:** complete with stop condition (no dual-verified historical weeks added)
**Suggested branch:** `data/m15-espn-history-expansion`
**Dependencies:** M14

Purpose: reduce sampling-frame uncertainty by evaluating the games the contest
actually selected, not only all-FBS games.

Scope:

- Recover additional historical weekly slates from lawful, reproducible
  screenshots, exports, archives, or user-provided evidence.
- Preserve display order, contest week, canonical game ID, public pick
  percentage and capture time, tiebreaker identity, source hash, transcription
  method, and verification status.
- Maintain unresolved/ambiguous evidence separately; never infer membership from
  rankings, network, or matchup prominence.
- Publish coverage by season/week and reconcile every imported game to canonical
  results and market inputs.

Acceptance:

- Duplicate, ambiguous, and identity-mismatched imports fail closed.
- Analysis reports verified-frame sample size and missing weeks explicitly.
- Public percentages without a valid pre-lock capture time are audit labels, not
  promotable model features.

Result: two single-source 2024 candidates were catalogued but not imported.
Historical `verified_espn_pickem` remains unavailable; see
`docs/espn_history_expansion.md`.

### M16 — Improve historical market depth and timing

**Status:** complete with stop condition (timestamped archives require paid access)
**Suggested branch:** `data/m16-market-depth`
**Dependencies:** M14; may run in parallel with M15/M17–M19

Purpose: strengthen the baseline and test whether market dynamics—not a weaker
or hindsight-contaminated market proxy—contain reproducible information.

Scope:

- Evaluate lawful sources for timestamped opening and latest-prelock moneyline,
  spread, and total observations with provider identity.
- Add only observations whose effective/retrieval semantics permit exact
  pre-kickoff selection; do not label an undated observation “open” or “close.”
- Rebuild provider consensus, vig-free probabilities, dispersion, movement, and
  staleness/coverage measures under the existing market contract.
- Compare the strengthened market-only baseline with the current baseline before
  judging any non-market candidate.

Acceptance:

- Post-kick observations and inferred ordering fail closed.
- Provider and timestamp coverage are reported by season/week.
- Any purchased or restricted source has documented license, cost, cache, and
  redistribution rules before implementation.

Result: no data purchased or substituted. Provider-neutral quote validation and
the measured local gap are documented in `docs/historical_market_depth.md`.

### M17 — Reopen point-in-time team-strength ratings

**Status:** complete with stop condition (no source has proven publication time)
**Suggested branch:** `data/m17-pit-ratings`
**Dependencies:** M14 and M06 feasibility memo; may run in parallel

Purpose: test ratings only when genuine weekly historical snapshots can be
joined as information available before each game.

Scope:

- Resolve the M06 Elo canonical-source decision with measured coverage and
  temporal semantics.
- Reassess weekly historical FPI/SP+ or other ratings only if licensing, stable
  identifiers, revision behavior, and reproducible archives are clear.
- Preserve rating publication/effective time, source version, retrieval time,
  team ID, week, and missingness reason.
- Predeclare residual signals such as rating-minus-market disagreement; do not
  treat correlated ratings as independent votes or average them arbitrarily.

Acceptance:

- End-of-season/current ratings cannot enter historical pregame rows.
- Each adapter passes sampled PIT leakage and team-identity audits.
- A failed source review ends with an explicit omission, not a substitute.

Result: all rating families remain omitted from matrix 2.0; see
`docs/pit_ratings_m17.md` and the tested future-observation contract.

### M18 — Point-in-time team form and efficiency

**Status:** complete; candidate family admitted to M20 evaluation
**Suggested branch:** `features/m18-team-form-efficiency`
**Dependencies:** M14; may run in parallel

Purpose: derive reproducible on-field signals that may explain information not
fully represented by the available market snapshot.

Scope:

- Build chronological, opponent-adjusted candidates from games strictly before
  kickoff: efficiency, explosiveness, success/finishing measures, turnovers with
  regression-to-mean treatment, pace, and special-teams indicators where source
  coverage supports them.
- Use training-fold-only estimation for opponent adjustment, shrinkage,
  normalization, and missing-value parameters.
- Separate preseason priors from in-season observations and expose sample size /
  uncertainty, especially in Weeks 1–3.
- Predeclare compact feature families; do not add large undifferentiated stat
  dumps.

Acceptance:

- Future-game mutation tests prove earlier rows are unchanged.
- Every rolling feature exposes its observation cutoff and games included.
- Source coverage, rule changes, and season comparability are documented.

Result: the compact prior-game PPA, success-rate, and explosiveness family
passed chronology and coverage gates (84.4% complete over 2017–2025). This is
eligibility for M20 evaluation, not feature promotion; see
`docs/team_form_efficiency_m18.md`.

### M19 — Preseason personnel and program context

**Status:** complete; coaching admitted to M20, other families omitted
**Suggested branches:** one PR per viable family under `features/m19-*`
**Dependencies:** M14; may run in parallel

Purpose: improve early-season estimates, where current-season team history is
sparse, using only consistently dated historical information.

Candidate families:

- returning/changed quarterback and prior-start experience
- returning production and transfer/roster continuity
- head-coach/coordinator continuity and years at school
- preseason ratings or priors with archived publication dates
- reproducible rest, travel, venue, and rivalry registries

Each family first receives a source/timing/licensing memo. Implement it only if
definitions can remain stable across seasons and coverage is sufficient under
M14. Injuries, depth-chart changes, weather forecasts, and qualitative news stay
manual/review-only until comparable timestamped historical archives exist.

Acceptance:

- One source family per PR with stable IDs, PIT tests, coverage report, and data
  dictionary.
- Missing and unknown remain distinct; absence is never interpreted as “no
  change,” “healthy,” or “returning.”
- No family enters modeling merely because collection work was completed.

Result: season-opening head-coach tenure and first-year status passed source and
coverage gates with explicit unknown handling. Returning production, talent,
QB/coordinator continuity, preseason ratings, rivalry, and travel remain omitted
for timing or definition failures. See `docs/program_context_m19.md`.

### M20 — Feature matrix 2.0 and predeclared incremental-value study

**Status:** complete; human disposition `no_features_promoted` recorded
**Suggested branch:** `modeling/m20-matrix-v2-ablation`
**Dependencies:** M14 and whichever M15–M19 source families pass their gates

Scope:

- Publish matrix schema `2.0.0` with explicit baseline, candidate, audit, target,
  timing, and sampling-frame roles.
- Re-run market-only, single-family additions, leave-family-out ablations, and a
  small predeclared combined residual model on identical held-out IDs.
- Estimate incremental value conditional on the strengthened market baseline;
  never compare only against winner accuracy or a stale/weaker baseline.
- Report paired log-loss/Brier deltas, calibration, coverage, season stability,
  coefficient/importance stability, missingness sensitivity, and verified-ESPN
  results where adequately powered.
- Apply the frozen multiplicity and disposition rules. Human dispositions remain
  required and are recorded in a new approved-feature-set artifact.

Acceptance:

- Fold-nested preprocessing and PIT tests pass for every included source.
- Confirmatory and exploratory results are visibly separated.
- The valid outcome may again be `no_features_promoted`.

Result: matrix 2.0 and the predeclared 2,000-resample study are complete. No
single, family, combined, or leave-family-out variant passed the frozen gates.
The decision packet awaits an explicit human disposition; see
`docs/incremental_value_report_m20.md`.

### M21 — Challenger, calibration, and registry promotion attempt

**Status:** complete; no challenger trained, `market_only` retained
**Suggested branch:** `modeling/m21-challenger-promotion`
**Dependencies:** M20

Scope when unblocked:

- Refit the interpretable fixed-market-offset logistic candidate first.
- Compare at most one justified nonlinear challenger using the identical folds,
  rows, promoted feature set, and a small training-only search space.
- Evaluate training-fold-only calibration only when predeclared diagnostics
  justify it.
- Package the best eligible candidate in the safe M13 serving format, register it
  as `candidate`, run the M12 promotion evaluator, and request a separate human
  decision for `shadow` designation or approval.
- Run eligible models in weekly shadow mode before any production replacement;
  never edit submitted picks automatically.

Acceptance:

- Complexity is rejected unless proper-score improvement is stable, meaningful,
  calibrated, and sufficiently covered under protocol 2.0.0.
- Automated tooling may produce only `eligible_for_human_review`; it cannot
  designate shadow or approve production use.
- If M20 promotes nothing or all candidates fail, write a hashed no-challenger
  decision and retain `market_only`.

Result: Matt Ryan approved M20's `no_features_promoted` disposition. The hashed
M21 decision records no training, no bundle, no registry change, and retention
of `market_only`; see `docs/m21_no_challenger_closeout.md`.

### Ongoing prospective capture

This is an operational track, not a feature-selection milestone:

- Continue saving each weekly slate, market snapshot, public percentages,
  recommendations, manual rationale, submission confirmation, tiebreaker, shadow
  output, results, and grading artifacts with capture timestamps and hashes.
- Freeze every pregame artifact at lock. Corrections are additive and audited.
- Do not inspect 2026 outcomes to tune this research cycle. When enough weeks or
  seasons accumulate, evaluate the frozen candidate exactly once under a
  separately versioned prospective protocol.

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
