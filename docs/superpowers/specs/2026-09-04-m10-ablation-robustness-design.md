# M10 feature ablation and robustness design

Date: 2026-09-04
Status: approved for implementation planning
Roadmap: `docs/modeling_implementation_roadmap.md` § M10
Branch: `modeling/m10-ablation-robustness`
Depends on: M08 residual stack, M09 inference utilities, matrix schema `1.0.0`,
protocol `1.0.0`

## Problem

M08/M09 score a small set of family and combined residual variants but do not
systematically ablate individual source features or leave families out, nor do
they produce a human decision worksheet for promote / review_only / reject.
M10 must supply compact paired evidence without inventing a new model family or
automating promotion.

## Goals

1. Run a predeclared ablation/robustness suite on the **existing** M08
   fixed-offset residual stack (same matrix, folds, eligibility, preprocess,
   λ, estimator).
2. Compare `market_only`, each single eligible source feature, each family,
   `combined`, and leave-one-family-out variants on identical canonical IDs.
3. Report aggregate and per-fold paired log-loss/Brier deltas vs `market_only`,
   M09-style calibration and week-clustered CIs, coverage/missingness, and
   cross-season consistency (accuracy secondary only).
4. Include bounded robustness: early vs week 4+, neutral, favorite bands,
   conference/context, verified ESPN (insufficient when undersized), season-drop
   aggregation from existing held-out predictions, and anomalous-season
   sensitivity (2020 predeclared).
5. Emit compact machine-readable artifacts plus `docs/incremental_value_report.md`
   and a decision worksheet with **`recommendation` unset**.
6. Keep large row-level outputs gitignored; commit report, schemas, and compact
   aggregates.

## Non-goals

- New model family, hyperparameter search, or estimator changes
- Automated promote / review_only / reject assignment
- Model registry mutation or weekly recommend changes
- Rating / deferred columns
- Retraining walk-forward models merely to omit a test season (season-drop is
  post-hoc aggregation of existing predictions)
- Committing bulk row-level prediction regenerations

## Approach

**Ablation runner over M08 primitives:** build an extended variant registry of
source-column allowlists; for each variant call the same eligibility,
`FoldPreprocessor`, and `fit_fixed_offset_logit` path used by M08; score paired
deltas with M09 cluster-bootstrap / calibration helpers; write compact tables
and a report template. Decision labels are human-only.

## Predeclared variant IDs

| ID | Source columns |
|---|---|
| `market_only` | none |
| `single__{col}` | one eligible M07/M08 source column |
| `family__site_temporal` | `SITE_TEMPORAL_COLUMNS` |
| `family__history` | `HISTORY_COLUMNS` |
| `family__market_context` | `MARKET_CONTEXT_COLUMNS` |
| `combined` | `COMBINED_COLUMNS` |
| `lof__without_site_temporal` | combined − site_temporal |
| `lof__without_history` | combined − history |
| `lof__without_market_context` | combined − market_context |

Eligible single-feature set = ordered union of the three families (same columns
as M08). Categorical concepts (`home_conference`, etc.) are ablated as **one
source column**; never ablate individual one-hot levels. Prohibited and deferred
fields never appear.

## Fit and pairing contract

- Inputs: M07 matrix path; protocol `1.0.0`; matrix schema `1.0.0`
- Shared canonical train/test eligibility across all variants (missing
  adjustment features are fold-locally imputed and must not change eligibility)
- Fail loudly if any variant’s held-out `game_id` set diverges from canonical
- Reuse M08 λ=1.0, L-BFGS-B, no intercept, market logit as fixed offset
- Large preds/details under `artifacts/residual_ablation/<run>/` (gitignored)

## Primary evidence

Versus `market_only`, for each ablation variant:

- Aggregate and per-fold paired Δ log-loss and Δ Brier (and secondary accuracy)
- Week-clustered bootstrap CIs with cluster key `(test_season, season_type, week)`
  and protocol seed/n_boot (reuse M09 helper)
- Aggregate calibration diagnostic (M09 GLM intercept/slope status)
- Coverage and adjustment-feature missingness rates
- Consistency across test seasons (fold table + season-drop)

## Bounded robustness

| Check | Rule |
|---|---|
| Early vs late | `weeks_1_3` vs `weeks_4_plus` |
| Neutral | neutral vs non-neutral |
| Favorite strength | M01 bands |
| Conference/context | predeclared home-conference group or `home_conference` top-level slice with sample sizes |
| Verified ESPN | `verified_espn_pickem`; if `n < MIN_ESPN_N` (predeclared **50**), status=`insufficient` — do not interpret deltas |
| Season-drop | From already-fitted walk-forward predictions, drop one held-out `test_season` and re-aggregate metrics; **label as aggregation-only, not retrain** |
| Anomalous season | Predeclared: **2020**; report metrics with/without that held-out season from existing preds |

## Decision worksheet

One row per single feature and per family (and optionally LOF/combined as
context rows). Evidence columns filled by the runner. Columns include at least:
`unit_type`, `unit_id`, `n`, `delta_log_loss`, `delta_brier`, bootstrap CI fields,
calibration status flags, missingness, season-consistency notes,
`recommendation` (**empty string / null**), `reviewer`, `review_notes`.

Judgment criteria for humans (not automated):

- **promote:** proper-score improvement directionally consistent across multiple
  seasons; uncertainty reasonably supportive; calibration not materially worse;
  not driven by one anomalous season or severe missingness
- **review_only:** mixed, weak, unstable, slice-specific, or operationally hard
- **reject:** no incremental proper-score value, worse calibration, unstable
  harm, leakage concern, or benefit only in one season/slice

The Markdown report may discuss interpretation under an explicit **Human review**
section but must not fill `recommendation` programmatically.

## CLI

```text
pick-prophet ablate-residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --matrix-schema 1.0.0 \
  --out-dir artifacts/residual_ablation/run
```

Optional: `--write-report docs/incremental_value_report.md` to refresh the
committed report skeleton from compact aggregates.

## Artifacts

| Artifact | Commit? | Role |
|---|---|---|
| `ablation_registry.json` | yes (or under docs/schemas) | Variant → columns |
| `overall_metrics.csv` | compact yes | Aggregate scores + Δ |
| `fold_metrics.csv` | compact yes | Per-fold Δ |
| `paired_bootstrap.csv` | compact yes | CIs |
| `slice_metrics.csv` | compact yes | Robustness slices |
| `season_drop.csv` | compact yes | Drop-held-out-season aggregates |
| `anomalous_season.csv` | compact yes | 2020 sensitivity |
| `calibration_summary.csv` | compact yes | Diagnostic a/b |
| `coverage_missingness.csv` | compact yes | Coverage / missingness |
| `decision_worksheet.csv` | yes | Evidence + blank recommendation |
| row-level preds/details | **gitignore** | Large |
| `docs/incremental_value_report.md` | yes | Human report |

## Tests

- Exact feature-family membership; single-source categorical ablation
- Identical IDs across variants; no prohibited/deferred fields
- Correct leave-family-out construction
- Deterministic season-drop aggregation
- Synthetic helpful / noise / single-season-benefit features
- Undersized verified-ESPN → `insufficient`
- Decision `recommendation` remains unset after the runner

## Explicit follow-ups

- Human fills worksheet / report recommendations
- M11 uses only human-approved feature set
- Post-hoc calibration remains deferred unless M09/M10 show stable need
