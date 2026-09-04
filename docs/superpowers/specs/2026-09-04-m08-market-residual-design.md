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

**Fold-local preprocessor + purpose-built fixed-offset estimator (Approach 1):**
build adjustment design matrix `X` only from the variant’s allowlisted
`MODEL_FEATURE_COLUMNS`; never place `home_market_logit` /
`home_implied_prob` in `X` or estimate a market coefficient. Predict
`σ(home_market_logit + Xβ)`. The estimator is not implemented by fitting a
standard `sklearn.linear_model.LogisticRegression`, because that API does not
support a per-row offset.

### Exact fitting objective

For `n` training rows, offset `o`, transformed adjustment matrix `X`, target
`y`, and coefficients `β`, minimize:

```text
J(β) = (1/n) Σᵢ [logaddexp(0, oᵢ + Xᵢβ) − yᵢ(oᵢ + Xᵢβ)]
       + (λ/2) ||β||²
```

with analytic gradient:

```text
∇J(β) = Xᵀ(σ(o + Xβ) − y)/n + λβ
```

Use deterministic L-BFGS-B with `β₀ = 0`, `λ = 1.0` (equivalent declaration
`C = 1/λ = 1.0` under this project’s explicitly mean-normalized objective),
`max_iter = 1000`, and documented gradient/function tolerance. Add SciPy as a
direct project dependency if its optimizer is used; do not rely on sklearn’s
transitive installation. Penalize adjustment coefficients only. There is no
intercept and no offset coefficient. Convergence failure is a hard fold error;
never emit predictions from a partial fit. Hyperparameters are fixed in advance
and are not tuned on held-out seasons.

## Variants (schema 1.0.0)

| Variant ID | Adjustment columns |
|---|---|
| `market_only` | none — `p_raw = σ(home_market_logit)` |
| `site_temporal` | `home_field_advantage`, `is_week_1`, `is_weeks_1_3`, `home_conference`, `away_conference`, `home_classification`, `away_classification` |
| `history` | `home_entering_wins`, `home_entering_losses`, `away_entering_wins`, `away_entering_losses`, `home_previous_result`, `away_previous_result`, `home_sos`, `away_sos`, `home_days_rest`, `away_days_rest` |
| `market_context` | `spread_home`, `total`, `line_provider_count`, `spread_home_open`, `total_open`, `spread_move_home`, `total_move` |
| `combined` | ordered union of `site_temporal` ∪ `history` ∪ `market_context` |

Column membership is declared in code as frozen tuples imported from / checked
against `MODEL_FEATURE_COLUMNS`. Adding a column requires a design change.

## Offset contract

- Offset source: `home_market_logit` from the matrix (BASELINE role).
- Never estimate a coefficient on the market logit or implied probability.
- Raw home/away moneylines are also prohibited from `X`: because they generate
  the baseline probability, admitting them would allow the adjustment to
  relearn the market slope through a proxy.
- Validate `home_implied_prob` against `σ(home_market_logit)` within a documented
  input tolerance when both are present. A mismatch is a hard input-contract
  error; `home_market_logit` remains the sole inference input.
- No explicit or implicit adjustment intercept: zero β ⇒ raw predictions
  identical to `σ(home_market_logit)`.
- `market_only` does not fit a model; it emits the raw sigmoid probability and
  zero adjustment.
- Persist the raw `σ(offset + adjustment)` as protocol-standard `p_home`.
  Metric functions may also derive `p_home_scored` using protocol-defined
  numerical clipping in a residual-detail artifact. Clipping is never applied
  before fitting and does not overwrite protocol-standard `p_home`.

## Preprocessing (per train fold, per variant)

Applied only to adjustment features:

1. Split numeric vs categorical by a schema-declared type map. Encode week flags
   and `home_field_advantage` as numeric `{0,1}`. `neutral_site` is deliberately
   absent from the variant because it is the exact complement of
   `home_field_advantage`.
2. Numeric values: fit median imputation and mean/scale on training rows only.
   Always append one unscaled `{0,1}` missingness indicator per numeric input so
   transformed feature order cannot change by fold. For an all-missing training
   column, use deterministic fill `0`, scale `1`, and indicator `1`; never let a
   library silently drop it.
3. Categorical values: normalize null and any test-only value to a reserved
   `unknown` sentinel. Fit the training vocabulary while always reserving
   `unknown`, then drop one deterministic non-unknown reference category per
   input (lexicographically first after normalization). If no non-unknown level
   exists, emit no dummy for that input. This prevents a full one-hot block from
   spanning a constant vector and creating an implicit intercept.
4. Reject a transformed matrix whose columns can construct a constant vector
   through known complementary/exhaustive encodings. Record transformed feature
   order and categorical reference levels.
5. No target-based selection; no leakage of test statistics into transformers.

Prohibited in any variant matrix: Pick’em percentages, targets, identities,
audit fields, deferred ratings, arbitrary extras, baseline market columns.

## Folds, eligibility, pairing

- Expanding folds from evaluation protocol 1.0.0 (`train season < test season`).
- Build one canonical eligibility set for each fold and split: `home_win ∈
  {0,1}`, finite `home_market_logit`, structurally valid matrix row, and valid
  baseline consistency. Missing adjustment features are imputed inside the fold
  and never change variant eligibility. Missing offset or target is excluded
  with a stable reason code.
- Every variant trains and predicts on the same canonical train/test IDs for the
  fold. Fail if emitted test IDs differ. Pairwise intersections may be reported
  diagnostically but must not define evaluation denominators or conceal
  variant-specific row loss.
- Report train and test input, eligible, and excluded counts with reason codes
  for every fold. Do not silently invent an offset or target.

## Artifacts

| Artifact | Contents |
|---|---|
| Protocol predictions | Existing M01 `PREDICTION_COLUMNS`, with `model=variant` and raw model probability in `p_home` |
| Residual prediction details | Joinable by variant/fold/game ID; adds `matrix_schema_version`, `p_home_scored`, `market_logit`, and `adjustment` without changing protocol 1.0.0’s required schema |
| Fold model bundle | Canonical JSON containing coefficients keyed by transformed feature name; source and transformed feature order; numeric medians/means/scales; categorical vocabularies/reference levels; train seasons; λ/objective/solver settings; convergence status, iterations and final objective; schema/protocol/library versions; hashes |
| Summary | per-variant/fold metrics; paired deltas vs `market_only` on shared IDs; coverage tables |
| Eligibility report | train/test counts and stable exclusion reasons per fold |
| Run manifest | input matrix hash, code/config and complete inference-bundle hashes, versions |

Model bundles use canonical, schema-validated JSON rather than pickle/joblib.
Inference reconstructs preprocessing and the dot product from the recorded
parameters. Hash the exact canonical bundle bytes (sorted keys, stable numeric
serialization) and reject unknown fields/schema versions or a hash mismatch.

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

- `market_only` protocol `p_home` exactly matches `σ(home_market_logit)`; only
  the residual-detail scored field uses protocol clipping.
- Zero adjustment / empty β reproduces market baseline.
- Market offset cannot appear as a fitted coefficient or in `X`.
- Raw moneylines cannot enter `X` as baseline proxies.
- Objective and analytic gradient match an independently calculated tiny
  fixture; convergence failure aborts the fold.
- Preprocessors fit on training rows only (mutation / spy test).
- Categorical levels only in test map to the reserved `unknown` level safely;
  reference levels are deterministic and encoded blocks cannot supply an
  implicit intercept.
- All-missing numeric training columns retain a stable transformed schema and
  explicit missingness indicator.
- Prohibited columns cannot enter a variant (hard gate).
- Changing `home_implied_prob` within the baseline-consistency tolerance while
  leaving the offset unchanged cannot change predictions; inconsistent baseline
  columns fail validation.
- Canonical JSON serialization round-trip: identical raw predictions within
  tolerance; tampered bundles, hashes, and unknown schema versions fail.
- Deterministic repeated runs (fixed seeds where library RNG applies).
- Every variant emits the canonical fold ID set; unequal IDs fail rather than
  being repaired by intersection.
- Train/test eligibility counts and exclusions reconcile for every fold.

## Docs

- Update roadmap § M08 status after acceptance.
- Short model card / methodology note: exact offset objective, `λ=1.0`, solver,
  variants, raw-vs-scored probability semantics, and deferral of ratings,
  calibration, and hyperparameter search.
- Pointer from matrix schema that M08 consumes baseline + model-feature roles.

## Open follow-ups

- M09: CIs, calibration, flip analysis.
- No post-hoc calibration occurs in M08; it begins only under M09’s
  training-only calibration contract.
- M10: formal family ablation / robustness.
- Rating variants after approved matrix schema bump.
