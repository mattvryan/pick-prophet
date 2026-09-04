# Residual diagnostics (M09)

**Status:** implemented for protocol `1.0.0` over M08 residual artifacts
**Design:** `docs/superpowers/specs/2026-09-04-m09-inference-calibration-design.md`

## Hard rule

Diagnostics evaluate **raw** M08 `p_home` only. This milestone does **not**
refit models, rewrite predictions, or emit a calibrated candidate. Calibration
intercept/slope is descriptive.

## Rebuild

```bash
pick-prophet diagnose-residual \
  --predictions-dir data/processed/residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --out-dir artifacts/residual_diagnostics/run
```

Requires M08 `predictions.csv`, `residual_details.csv`, `eligibility.csv`, and
`run_manifest.json`, plus the **exact** matrix whose SHA matches the residual
manifest.

## Predeclared constants

| Setting | Value |
|---|---|
| Cluster key | `(test_season, season_type, week)` |
| `n_boot` / seed | protocol defaults (`500` / `20260904`) |
| CI | 2.5th/97.5th linear percentile of uncentered `Δ*` |
| p-value | centered null `(1 + #{|Δ*−Δ| ≥ |Δ|}) / (n_boot+1)` |
| Holm | one family of estimable confirmatory **log-loss** Δs; α=0.05 |
| Reliability | 10 equal-width bins |
| Calibration | unpenalized Bernoulli GLM `y ~ σ(a + b logit(p_ε))`, `ε=1e-6` |
| Flip | home if `p > 0.5+1e-12`, away if `p < 0.5-1e-12`, else tie |

## Artifacts

`summary.json`, `overall_metrics.csv`, `paired_bootstrap.csv`,
`slice_metrics.csv`, `reliability_bins.csv`, `calibration_fit.csv`,
`adjustment_bands.csv`, `flip_summary.csv`, `fold_consistency.csv`,
`exclusions.csv`, `report.md`.

## Follow-ups

Post-hoc train-fold calibration only if these diagnostics show a material,
stable miscalibration problem. M10 owns ablation/robustness.
