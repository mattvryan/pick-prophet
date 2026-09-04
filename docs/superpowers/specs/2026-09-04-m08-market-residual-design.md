# M08 market-residual logistic design

Date: 2026-09-04
Status: approved for implementation planning
Roadmap: `docs/modeling_implementation_roadmap.md` § M08
Branch: `modeling/m08-market-residual-logit`
Depends on: M07 matrix schema `1.0.0`, evaluation protocol `1.0.0`

## Problem

Baselines treat market and other signals as ordinary features. M08 needs an
interpretable residual model where the market logit is a **fixed offset** and
only M07-approved adjustment features may move probability, with fold-nested
preprocessing and clean paired candidates for M09/M10.

## Goals

1. Implement `logit(P(home_win)) = home_market_logit + x_adj · β` with **no**
   free adjustment intercept (so `β = 0` reproduces the market exactly).
2. Ship five predeclared variants on matrix schema 1.0.0 (no ratings).
3. Fit preprocess + β independently inside each M01 training fold.
4. Pair variants on identical held-out `game_id` sets; report coverage loss.
5. Persist predictions, adjustments, coefficients, preprocess metadata, feature
   lists, fold windows, schema/protocol versions, and hashes.
6. Provide tests for offset integrity, leakage, prohibited columns,
   serialization, and determinism.

## Non-goals

- Hyperparameter search or automated feature selection
- Rating / rating-vs-market variants (blocked until matrix schema bump)
- M09 confidence intervals / calibration diagnostics
- M10 formal ablation / robustness suites
- Production `weekly recommend` changes
- Boosting or qualitative news features

## Approach

**sklearn-style Pipeline + fixed-offset estimator (Approach 1):** build
adjustment design matrix `X` only from the variant’s allowlisted
`MODEL_FEATURE_COLUMNS`; never place `home_market_logit` /
`home_implied_prob` in `X` or estimate a market coefficient. Predict
`σ(home_market_logit + Xβ)` with probability clipping only at scoring time.

**Regularization:** fixed `LogisticRegression`-equivalent L2 with `C=1.0`
(penalty on adjustment coefficients only). Documented in advance; not tuned on
held-out seasons.

## Variants (schema 1.0.0)

| Variant ID | Adjustment columns |
|---|---|
| `market_only` | none — `p = clip(σ(home_market_logit))` |
| `site_temporal` | `home_field_advantage`, `neutral_site`, `is_week_1`, `is_weeks_1_3`, `home_conference`, `away_conference`, `home_classification`, `away_classification` |
| `history` | `home_entering_wins`, `home_entering_losses`, `away_entering_wins`, `away_entering_losses`, `home_previous_result`, `away_previous_result`, `home_sos`, `away_sos`, `home_days_rest`, `away_days_rest` |
| `market_context` | `spread_home`, `total`, `home_moneyline`, `away_moneyline`, `line_provider_count`, `spread_home_open`, `total_open`, `spread_move_home`, `total_move` |
| `combined` | ordered union of `site_temporal` ∪ `history` ∪ `market_context` |

Column membership is declared in code as frozen tuples imported from / checked
against `MODEL_FEATURE_COLUMNS`. Adding a column requires a design change.

## Offset contract

- Offset source: `home_market_logit` from the matrix (BASELINE role).
- Never estimate a coefficient on the market logit or implied probability.
- No adjustment intercept: zero β ⇒ predictions identical to clipped market.
- `market_only` does not fit a model; it emits the clipped market probability
  and zero adjustment.

## Preprocessing (per train fold, per variant)

Applied only to adjustment features:

1. Split numeric vs categorical by declared type map (booleans treated as
   numeric `{0,1}` or categorical — **choose numeric 0/1** for
   `neutral_site` / week flags / `home_field_advantage` when already encoded).
2. Numeric: median imputation + missingness indicator; then standardization.
3. Categorical (conferences, classifications): map null/unseen → explicit
   `unknown` level; one-hot encode using train levels only.
4. No target-based selection; no leakage of test statistics into transformers.

Prohibited in any variant matrix: Pick’em percentages, targets, identities,
audit fields, deferred ratings, arbitrary extras, baseline market columns.

## Folds, eligibility, pairing

- Expanding folds from evaluation protocol 1.0.0 (`train season < test season`).
- Row eligible for a variant if: `home_win ∈ {0,1}`, finite `home_market_logit`,
  and structural matrix row present. Missing adjustment features are imputed
  inside the fold (not an exclusion). Missing offset or target ⇒ exclude with
  reason code.
- Within each test fold, paired comparisons use the **intersection** of
  eligible `game_id`s across the variants being compared (at minimum each
  adjustment variant ∩ `market_only`). Report coverage loss and exclusion
  reasons; do not silently invent offset or target.

## Artifacts

| Artifact | Contents |
|---|---|
| Predictions | `protocol_version`, `matrix_schema_version`, `variant`, `fold_id`, `test_season`, `game_id`, `week`, `y_true`, `p_home`, `market_logit`, `adjustment`, `sampling_frame` |
| Fold model bundle | coeffs keyed by post-encode feature names, feature list, preprocess metadata, train seasons, hashes, `C=1.0`, `fit_intercept=false` for adjustment |
| Summary | per-variant/fold metrics; paired deltas vs `market_only` on shared IDs; coverage tables |
| Run manifest | input matrix hash, code/config hashes, versions |

## CLI

```bash
pick-prophet fit-residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --matrix-schema 1.0.0 \
  --output-dir data/processed/residual
```

Outputs gitignored under processed paths; CI uses fixtures.

## Tests and acceptance

- `market_only` exactly matches clipped `σ(home_market_logit)`.
- Zero adjustment / empty β reproduces market baseline.
- Market offset cannot appear as a fitted coefficient or in `X`.
- Preprocessors fit on training rows only (mutation / spy test).
- Categorical levels only in test map to `unknown` safely.
- Prohibited columns cannot enter a variant (hard gate).
- Serialization round-trip: same `p_home` within tolerance.
- Deterministic repeated runs (fixed seeds where library RNG applies).
- Paired folds reject or report unequal ID sets per protocol pairing rules.

## Docs

- Update roadmap § M08 status after acceptance.
- Short model card / methodology note: offset contract, `C=1.0`, variants,
  deferral of ratings and HP search.
- Pointer from matrix schema that M08 consumes baseline + model-feature roles.

## Open follow-ups

- M09: CIs, calibration, flip analysis.
- M10: formal family ablation / robustness.
- Rating variants after approved matrix schema bump.
