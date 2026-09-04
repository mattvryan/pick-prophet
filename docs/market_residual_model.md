# M08 market-residual logistic model card

**Status:** implemented for matrix schema `1.0.0` / protocol `1.0.0`
**Design:** `docs/superpowers/specs/2026-09-04-m08-market-residual-design.md`

## Contract

```text
logit(P(home_win)) = home_market_logit + X β
```

- `home_market_logit` is a **fixed offset** (never a fitted coefficient, never in `X`).
- No adjustment intercept; `β = 0` reproduces `σ(home_market_logit)`.
- Raw moneylines and `neutral_site` are excluded from adjustment features.
- Protocol `p_home` stores the **raw** sigmoid; clipping appears only as
  `p_home_scored` in residual detail artifacts.

## Objective

Mean Bernoulli NLL on the offset linear predictor plus L2:

```text
J(β) = (1/n) Σ [logaddexp(0, o + Xβ) − y(o + Xβ)] + (λ/2) ||β||²
```

with `λ = 1.0` (`C = 1/λ = 1.0` under this mean-normalized form), L-BFGS-B,
`β₀ = 0`, `max_iter = 1000`. SciPy is a direct dependency. Convergence failure
aborts the fold.

## Variants

`market_only`, `site_temporal`, `history`, `market_context`, `combined` — see
`src/pick_prophet/models/residual_variants.py`. Ratings deferred until a matrix
schema bump.

## Rebuild

```bash
pick-prophet fit-residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --matrix-schema 1.0.0 \
  --output-dir data/processed/residual
```

## Deferred to later milestones

- M10: formal ablation / robustness
- Hyperparameter search and automated feature selection

## Diagnostics (M09)

Inference/calibration diagnostics over raw residual `p_home`:

```bash
pick-prophet diagnose-residual \
  --predictions-dir data/processed/residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --out-dir artifacts/residual_diagnostics/run
```

See `docs/residual_diagnostics.md`. No calibrated prediction candidate is
produced in M09.

## Ablation (M10)

```bash
pick-prophet ablate-residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --out-dir artifacts/residual_ablation/run \
  --write-report docs/incremental_value_report.md
```

See `docs/incremental_value_report.md`. Recommendations are human-only.
