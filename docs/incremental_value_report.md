# Incremental value report (M10)

**Status:** compact evidence tracked at `docs/modeling_artifacts/m10/1.0.0/`; **human recommendations unset**
**Design:** `docs/superpowers/specs/2026-09-04-m10-ablation-robustness-design.md`
**Evidence version:** `1.0.0`
**Tracked artifacts:** [`docs/modeling_artifacts/m10/1.0.0/`](modeling_artifacts/m10/1.0.0/)
**Manifest:** [`docs/modeling_artifacts/m10/1.0.0/manifest.json`](modeling_artifacts/m10/1.0.0/manifest.json)

## Inference window (read first)

**Proper-score inference covers held-out seasons 2022–2025 only** (moneyline /
implied-probability coverage in this CFBD pull; earlier expanding folds are
skipped when train/test eligible sets are empty).

**2020 anomalous-season sensitivity cannot be evaluated** in this pull: there
are no eligible held-out predictions for 2020. Artifacts emit
`status=not_available` with a null delta and reason — not an unchanged
aggregate presented as an exclusion result.

## Tracked compact evidence (`1.0.0`)

Committed under `docs/modeling_artifacts/m10/1.0.0/` (no row-level predictions
or fitted bundles):

| File | Role |
|---|---|
| `ablation_registry.json` | Variant → columns; unavailable open/move list; n_boot |
| `decision_worksheet.csv` | Evidence rows; `recommendation` blank |
| `overall_metrics.csv` | Aggregate scores and Δ vs `market_only` |
| `fold_metrics.csv` | Per-fold paired Δs |
| `paired_bootstrap.csv` | Cluster bootstrap (n_boot=500) |
| `season_drop.csv` | Held-out season-drop aggregates (not retrains) |
| `anomalous_season.csv` | 2020 sensitivity (`not_available` here) |
| `calibration_summary.csv` | Diagnostic intercept/slope |
| `coverage_missingness.csv` | Coverage / missingness |
| `slice_metrics.csv` | Bounded robustness slices |
| `manifest.json` | SHA-256 of each artifact + source matrix + M10 code revision |

Verify integrity by recomputing SHA-256 of each listed file and matching
`manifest.json` (`source_matrix_sha256`, `m10_code_revision`,
`artifacts_sha256`).

## Corrections applied before this evidence version

1. Canonical matrix `true`/`false` Boolean predictors parse as numeric 1/0.
2. All-missing training features emit **no** transformed columns (marked
   unavailable) so the fit reproduces `market_only`.
3. Opening/movement fields (`spread_home_open`, `total_open`,
   `spread_move_home`, `total_move`) are **unavailable for evidence** and
   excluded from family variants and M11 eligibility.
4. Protocol bootstrap **n_boot=500**.

## Rebuild (local; large outputs gitignored)

```bash
pick-prophet ablate-residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --out-dir artifacts/residual_ablation/run
```

Copy compact CSVs/JSON into a new versioned directory under
`docs/modeling_artifacts/m10/` and refresh `manifest.json` when regenerating.

## Hard rules

- Decision labels (`promote` / `review_only` / `reject`) are **human-only**.
- `decision_worksheet.csv` leaves `recommendation` unset until review.
- Do not auto-populate recommendations from the runner.
- M11 remains blocked until a versioned approved feature-set artifact exists.

### Worksheet status

Recommendations remain **unset** pending human review of the tracked
`1.0.0` decision packet.
