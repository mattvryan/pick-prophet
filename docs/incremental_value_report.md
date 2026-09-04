# Incremental value report (M10)

**Status:** evidence regenerated after ablation corrections; **human recommendations unset**
**Design:** `docs/superpowers/specs/2026-09-04-m10-ablation-robustness-design.md`

## Inference window (read first)

**Proper-score inference covers held-out seasons 2022–2025 only** (moneyline /
implied-probability coverage in this CFBD pull; earlier expanding folds are
skipped when train/test eligible sets are empty).

**2020 anomalous-season sensitivity cannot be evaluated** in this pull: there
are no eligible held-out predictions for 2020. Artifacts emit
`status=not_available` with a null delta and reason — not an unchanged
aggregate presented as an exclusion result.

## Corrections applied before this regeneration

1. Canonical matrix `true`/`false` Boolean predictors parse as numeric 1/0.
2. All-missing training features emit **no** transformed columns (marked
   unavailable) so the fit reproduces `market_only`.
3. Opening/movement fields (`spread_home_open`, `total_open`,
   `spread_move_home`, `total_move`) are **unavailable for evidence** and
   excluded from family variants and M11 eligibility.
4. Protocol bootstrap **n_boot=500**.

## Rebuild

```bash
pick-prophet ablate-residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --out-dir artifacts/residual_ablation/run \
  --write-report docs/incremental_value_report.md
```

Row-level fit outputs under `artifacts/residual_ablation/` are gitignored.
Compact aggregates from the corrected run live under
`artifacts/residual_ablation/decision_packet_run_v2/compact/` (local).

## Hard rules

- Decision labels (`promote` / `review_only` / `reject`) are **human-only**.
- `decision_worksheet.csv` leaves `recommendation` unset until review.
- Do not auto-populate recommendations from the runner.
- M11 remains blocked until a versioned approved feature-set artifact exists.

### Worksheet status

Recommendations remain **unset** pending human review of the regenerated
decision packet.
