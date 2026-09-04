# Research protocol 2.0

Status: **frozen before M15–M19 evaluation**
Frozen date: 2026-09-04
Prospective stream: **2026 weekly shadow — development prohibited**

## Population and folds

- Historical research seasons: 2017–2025.
- Expanding test folds: 2018–2025, always trained on seasons strictly earlier.
- Proper-score comparisons use only folds with identical finite market and
  candidate predictions; current historical coverage is 2022–2025.
- `all_fbs` and `verified_espn_pickem` are separate populations. The latter is
  confirmatory only when its predeclared minimum sample requirements are met.
- No 2026 result may influence sources, features, preprocessing, thresholds,
  tuning, calibration, or model choice.

## Primary estimands and uncertainty

For candidate minus market on identical game IDs:

1. held-out log-loss delta;
2. held-out Brier-score delta.

Lower is better. Accuracy is descriptive only. Confidence intervals use 2,000
deterministic resamples clustered by `(test_season, season_type, week)`. All
preprocessing and any tuning/calibration are nested inside training seasons.

## M20 promotion eligibility

A feature family may be recommended for human promotion only if all conditions
hold:

- aggregate log-loss and Brier deltas are both negative;
- the 95% clustered-bootstrap upper bound is below zero for both metrics;
- at least one materiality threshold is met: log-loss delta ≤ `-0.0005` or
  Brier delta ≤ `-0.0002`;
- at least three of four inference seasons have non-positive delta for each
  proper score and at least two seasons strictly improve each score;
- at least 2,500 paired games overall and 500 in each of four test seasons;
- finite paired-prediction coverage is at least 95%;
- calibration ECE regression is no greater than 0.01;
- all required values pass PIT, identity, licensing, and leakage audits.

For `verified_espn_pickem`, require at least 400 games across at least three
seasons and 100 games per included season. Until then it is an explicitly
underpowered descriptive slice, not a promotion surface.

Holm correction applies within each predeclared family across single-feature
confirmatory tests. Family tests and the one predeclared combined residual model
are reported separately. Exploratory results may seed a later protocol version
but cannot be promoted in this cycle.

Human disposition remains mandatory. Passing these rules means eligible for a
human `promote` decision, never automatic promotion.

## Candidate model scope

- Fixed-market-offset logistic is primary.
- M20 permits single-family variants and one combined variant declared before
  fitting.
- M21 may compare at most one nonlinear challenger, only if M20 promotes a
  nonempty feature set.
- No deep-learning model is justified by the current sample size or tabular
  structure.

## Missingness and coverage

Missing and unknown are distinct. Fold-nested imputation may be used only when
declared by the family contract. Rows cannot disappear silently: every exclusion
has a reason, and candidate/market comparisons are paired after eligibility.

## Prospective assessment

Weekly 2026 artifacts are captured and graded operationally but remain sealed
from this research cycle. A later protocol will predeclare when and how the
frozen shadow candidate receives a one-time prospective assessment.
