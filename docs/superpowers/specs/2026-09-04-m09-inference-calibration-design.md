# M09 inference and calibration diagnostics design

Date: 2026-09-04
Status: approved for implementation planning
Roadmap: `docs/modeling_implementation_roadmap.md` § M09
Branch: `modeling/m09-inference-calibration`
Depends on: M08 residual artifacts, evaluation protocol `1.0.0`

## Problem

M08 emits raw walk-forward `p_home` for five residual variants but does not
quantify paired uncertainty, calibration shape, adjustment/flip behavior, or
multiplicity-aware slice claims versus `market_only`. M09 must make those
diagnostics reproducible without changing predictions or introducing a
calibrated candidate.

## Goals

1. Diagnose **raw** M08 `p_home` only — never refit, transform, replace, or
   overwrite predictions; never emit a calibrated prediction candidate.
2. Report paired accuracy, log-loss, and Brier deltas versus `market_only` by
   fold and aggregate.
3. Provide week-clustered bootstrap percentile CIs with protocol seed/n_boot,
   resampling clusters keyed by `(test_season, season_type, week)` identically
   for candidate and baseline.
4. Emit reliability tables (fixed equal-width bins), diagnostic calibration
   intercept/slope, adjustment-magnitude bands, and winner-flip analysis.
5. Score required M01 slices with confirmatory vs exploratory labels and Holm
   control across one explicitly defined confirmatory log-loss Δ family.
6. Persist machine-readable tables plus a concise Markdown report with fold
   consistency, coverage, denominators, and reason-coded exclusions.
7. Leave post-hoc calibration to a later PR only if these diagnostics show a
   material, stable problem (any future calibrator must be train-fold-only).

## Non-goals

- Post-hoc calibrated `p_home` or any prediction rewrite
- Extending `fit-residual` to compute diagnostics inline as the primary path
- Notebook-only logic or required image/plot artifacts
- M10 ablation / robustness suites
- Rating adapters or matrix schema changes
- Production weekly recommend / card changes
- Changing M01 `bootstrap_paired_delta` week-only semantics used by legacy
  `evaluate` (M09 adds a distinct cluster-aware helper)

## Approach

**Diagnostics package over M08 artifacts (Approach 1):** read an M08 residual
run directory (`predictions.csv`, `residual_details.csv`, eligibility /
summary), join the exact M07 matrix for slice and cluster fields,
compute all diagnostics on raw `p_home`, and write a new diagnostics output
tree. CLI: `pick-prophet diagnose-residual`.

## Predeclared constants

| Setting | Value |
|---|---|
| Confidence | 95% |
| `n_boot` | 500 (`ProtocolConfig.n_boot`) |
| Seed | `20260904` (`ProtocolConfig.bootstrap_seed`) |
| Interval | 2.5th/97.5th percentile CI using deterministic linear quantiles of paired cluster-bootstrap `Δ*`, where `Δ = metric(candidate) − metric(market_only)`; negative log-loss/Brier and positive accuracy deltas are improvement |
| Cluster key | `(test_season, season_type, week)` — same clusters and rows for both arms every replicate |
| Reliability | 10 equal-width bins on `[0, 1]`; index `min(int(p * n_bins), n_bins - 1)` (same as `calibration_bins`) |
| Calibration diagnostic | Bernoulli GLM / logistic: `y ~ Bernoulli(σ(a + b · logit(p)))` (Cox-style intercept `a`, slope `b`; ideal `a=0`, `b=1`), with `p` clipped **only for this fit** to `(ε, 1−ε)`, `ε = 1e-6`; never applied to stored or scored `p_home`. Emit an explicit estimation status rather than changing predictions. |
| Flip | classify home when `p > 0.5 + 1e-12`, away when `p < 0.5 - 1e-12`, otherwise tie; flip only when both arms are non-ties and choose different winners; report candidate-tie and market-tie buckets separately |
| Adjustment bands | residual-detail `adjustment` is a log-odds shift: `[0, 0.05)`, `[0.05, 0.15)`, `[0.15, 0.30)`, `[0.30, ∞)` by absolute log-odds adjustment; report signed log-odds direction and the separate probability change `candidate_p − market_p` |
| Confirmatory family | one family containing every estimable `(non-market variant, overall-or-M01-required-slice)` paired **log-loss** Δ; Holm–Bonferroni at `α = 0.05` |
| Exploratory | any additional contrasts labeled `exploratory` (reported, no multiplicity claim) |

### Holm procedure (confirmatory log-loss)

1. For each confirmatory contrast, compute the observed paired delta `Δ` and
   paired clustered bootstrap replicates `Δ*`. Construct the centered null
   distribution `Δ* − Δ`, then compute the finite-sample-corrected two-sided
   p-value:
   `p = (1 + #{|Δ* − Δ| ≥ |Δ|}) / (n_boot + 1)`.
   The percentile CI still uses the uncentered `Δ*`. Do not use the percentile
   distribution’s raw sign frequency as a p-value and do not invent asymptotic
   p-values.
2. Apply Holm step-down once across all estimable hypotheses in the declared
   family (all non-market variants × overall/required slices), not separately
   by variant or slice. Emit raw p-value, Holm-adjusted p-value, rank, family
   size, and `holm_reject_0.05`.
3. Accuracy and Brier bootstrap CIs are reported for the same slices but are
   **not** part of the Holm family in this milestone.
4. Predeclared but empty or non-estimable hypotheses remain in the inventory
   with a reason and no p-value; they are not counted in the realized Holm
   denominator. Report both the predeclared and realized family sizes. Treat
   duplicate populations such as `overall` and `all_fbs` as separately labeled
   but deduplicate identical game-ID sets for hypothesis testing so the same
   contrast is not counted twice.

Bootstrap metrics are row-weighted over the sampled clusters; aggregate metrics
are computed over pooled held-out rows rather than averaging fold metrics.
Sampling a cluster includes all of its paired rows, including repeated inclusion
when that cluster is drawn more than once. Use a deterministic RNG stream keyed
by the protocol seed plus a stable contrast identifier so results do not change
when output iteration order changes.

## Inputs

Primary: `--predictions-dir` pointing at an M08 residual output directory
containing at least:

- `predictions.csv` — protocol prediction schema (`model`, `fold_id`,
  `test_season`, `game_id`, `week`, `y_true`, `p_home`, `sampling_frame`, …)
- `residual_details.csv` — `adjustment`, `market_logit`, `p_home` (raw), keyed
  by `(model, fold_id, test_season, game_id)`
- M08 eligibility report — train/test input, eligible, and reason-coded excluded
  counts by fold; required to report coverage without reconstructing or
  inventing exclusions in M09

Required for protocol 1.0.0 confirmatory slices and cluster completeness:

- `--matrix` path to the M07 matrix used for the residual fit, joined on
  `game_id` (and consistent season identity via matrix `season` ↔ prediction
  `test_season`). Must supply `season_type`, `neutral_site`, `spread_home` (for
  favorite bands). `sampling_frame` may come from predictions when already
  present. M09 must not substitute fields from a different matrix build.

Validate both input files against the M08 manifest and hashes. Keys must be
unique, joins must be one-to-one, prediction/detail probabilities must agree
within a documented tolerance, and matrix `season` must equal prediction
`test_season`. When the matrix is used, verify its hash matches the matrix hash
recorded by M08. Reject non-finite probabilities and values outside `[0,1]`;
do not clamp invalid stored predictions into validity.

Hard failures (no silent drop):

- Missing `market_only` for a fold’s candidate game-ID set
- Unequal paired `game_id` sets between candidate and `market_only`
- Missing required cluster fields (`test_season`, `season_type`, `week`)
- Missing columns needed to build a confirmatory slice
- Empty overall paired set
- Duplicate prediction/detail keys, one-to-many matrix joins, input hash
  mismatches, or inconsistent raw probabilities

Do **not** invent `season_type` or slice membership.

## Outputs

Default tree: `--out-dir` (e.g. `artifacts/residual_diagnostics/<run_id>/`):

| Artifact | Role |
|---|---|
| `summary.json` | Protocol version, input hashes/paths, variants, n_boot/seed/CI method, confirmatory vs exploratory inventory, coverage and exclusion reason codes |
| `overall_metrics.csv` | Per variant (fold + aggregate): n, accuracy, log-loss, Brier, Δ vs `market_only` |
| `paired_bootstrap.csv` | Contrasts: metric, observed Δ, bootstrap mean, percentile CI, n_boot, seed, stable contrast ID, n_clusters, n_rows |
| `slice_metrics.csv` | Confirmatory (+ labeled exploratory) slice scores, Δs, centered-bootstrap p / Holm fields for log-loss, predeclared/realized family sizes and non-estimable reasons |
| `reliability_bins.csv` | Per variant for aggregate and each fold: all 10 bins including empty bins, raw-probability means/outcomes, count and explicit boundary convention |
| `calibration_fit.csv` | Aggregate and per-fold diagnostic `a`, `b`, n, ε, ideal values, solver/status/reason; fit never alters predictions |
| `adjustment_bands.csv` | Log-odds band, counts, mean absolute/signed adjustment, mean probability change versus the joined `market_only` prediction, flip rate and coverage denominators |
| `flip_summary.csv` | Flip, agree, candidate-tie and market-tie counts/rates vs `market_only`, using the declared tolerance |
| `fold_consistency.csv` | Per-fold Δ signs/magnitudes for log-loss/Brier/accuracy to surface season instability |
| `exclusions.csv` | Reason-coded row/fold exclusions with denominators |
| `report.md` | Concise human summary; must state raw preds unchanged and no calibrated candidate |

No required plots or notebooks. Tables are sufficient.

Calibration fits use a deterministic unpenalized two-parameter Bernoulli
log-likelihood optimizer with documented convergence tolerance and maximum
iterations. Complete/quasi separation, a single outcome class, insufficient
rows, singular curvature, or non-convergence yields `status=not_estimable` (or
`failed`) with null `a`/`b` and a reason code; it does not abort unrelated
diagnostics and never falls back to a penalized estimate silently.

## Package / CLI

- `src/pick_prophet/models/residual_diagnostics.py` — load, pair, score, bootstrap,
  reliability, calibration diagnostic, flips/bands, multiplicity, writers
- Shared helpers may live under `evaluation/` when reusable (e.g. cluster-key
  bootstrap) without changing legacy week-only `bootstrap_paired_delta` behavior
- Reuse `score_probabilities`, `calibration_bins`, M01 slice definitions /
  favorite-band helpers where possible

```text
pick-prophet diagnose-residual \
  --predictions-dir data/processed/residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --out-dir artifacts/residual_diagnostics/run
```

The command must not call residual fitting or write new prediction files.

## Tests

- Deterministic clustered resampling for fixed seed; cluster key uses
  `(test_season, season_type, week)` not week alone
- Same clusters/rows applied to candidate and `market_only` every replicate
- Stable contrast-specific RNG streams are invariant to variant/output order;
  percentile quantiles and centered-bootstrap p-values match a fixed fixture
- Unequal paired game IDs fail
- Duplicate keys, one-to-many joins, invalid probabilities, inconsistent detail
  rows, and manifest/input hash mismatches fail
- Perfect / constant / adversarial prediction fixtures yield expected metrics
- Empty reliability bins and probabilities near 0/1 handled without mutating
  stored `p_home`; calibration fit uses ε clip only internally
- Single-class, separated, and non-converged calibration fits are status-coded
  without changing or suppressing other diagnostics; empty confirmatory slices
  are reason-coded
- Flip tolerance around `0.5`, candidate/market tie buckets, log-odds adjustment
  bands, and probability-change direction
- Holm ordering, adjusted p-values, global family scope, identical-population
  deduplication, and non-estimable hypothesis handling on tiny fixtures
- CLI smoke: fixture residual dir → all required artifacts present and
  schema-stable

## Documentation updates (implementation PR)

- `docs/market_residual_model.md` — point to M09 diagnostics command / artifacts
- `docs/modeling_implementation_roadmap.md` — mark M09 scope items done when
  acceptance passes
- Short `docs/residual_diagnostics.md` (or equivalent) describing constants,
  cluster key, and “raw only / no calibrated candidate”

## Explicit follow-ups (out of scope)

- Post-hoc train-fold calibration candidate (only if M09 shows stable miscalibration)
- M10 ablation / robustness
- Promoting any residual variant over market baseline
