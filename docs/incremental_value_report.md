# Incremental value report (M10)

**Status:** runner implemented; **human recommendations unset**
**Design:** `docs/superpowers/specs/2026-09-04-m10-ablation-robustness-design.md`
**Branch:** `modeling/m10-ablation-robustness`

## Purpose

Provide paired evidence that a feature or family adds incremental value beyond
`market_only` under the M08 fixed-offset residual stack. This document does
**not** auto-promote features or change weekly recommendations.

## Rebuild

```bash
pick-prophet ablate-residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --out-dir artifacts/residual_ablation/run \
  --write-report docs/incremental_value_report.md
```

Row-level fit outputs under `artifacts/residual_ablation/` are gitignored.
Commit compact CSVs from a reviewed run when regenerating evidence in-repo.

## Variant families

- `market_only`
- `single__{source_column}` (categorical = whole source column, not one-hots)
- `family__site_temporal` / `family__history` / `family__market_context`
- `combined`
- `lof__without_*` leave-one-family-out

## Season-drop vs retrain

`season_drop.csv` re-aggregates **already valid** walk-forward held-out
predictions after excluding a test season. It does **not** refit models with
that season removed from training.

## Human review

Fill `recommendation` (`promote` / `review_only` / `reject`) in
`decision_worksheet.csv` only after reviewing:

- aggregate and per-fold Δ log-loss / Δ Brier vs `market_only`
- bootstrap CIs
- calibration diagnostics
- coverage / missingness
- season-drop and anomalous-season (2020) tables
- robustness slices (early/late, neutral, favorite bands, conference, ESPN)

Accuracy alone cannot promote. Verified-ESPN slices with `n < 50` are
`insufficient` and must not drive decisions.

### Worksheet status

Recommendations remain **unset** until a human reviewer fills them.
