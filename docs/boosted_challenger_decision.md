# Boosted challenger decision (M11)

**Status:** not run — blocked by M10 evidence (`no_features_promoted`)
**Decision artifact:** [`docs/modeling_artifacts/m11/1.0.0/decision.json`](modeling_artifacts/m11/1.0.0/decision.json)
**M10 approved feature set:** [`docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json`](modeling_artifacts/m10/1.0.0/approved_feature_set.json)
**Baseline retained:** `market_only`

## Decision

M10 evaluated the available feature families against `market_only`. No feature
met the human promotion standard. A nonlinear / gradient-boosting model would
therefore add complexity without an approved signal set.

`review_only` features (and families) are **not** eligible for M11. They must
not be reinterpreted as approved. Market-only boosting is not a meaningful
challenger: it would not test incremental non-market signal under the M10 gate.

**Skipping M11 is an evidence-driven successful outcome, not a failed
implementation.** The market baseline remains the active reference model.

## Scope of evidence

Proper-score inference for the controlling M10 packet covered held-out seasons
**2022–2025** only. Anomalous-season 2020 sensitivity was unavailable in that
packet.

## Reopening

M11 may be reopened only after a **new M10 evidence version** promotes at least
one feature into `promoted_features`. Until then, any future M11 run must fail
closed on an empty promote set.

## What this PR does not do

- No boosting dependency
- No model training
- No dummy predictions or fitted bundles
- No promotion of `review_only` or rejected features
