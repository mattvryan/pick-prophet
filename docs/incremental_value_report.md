# Incremental value report (M10)

**Status:** compact evidence tracked at `docs/modeling_artifacts/m10/1.0.0/`; **human dispositions recorded** (`no_features_promoted`)
**Design:** `docs/superpowers/specs/2026-09-04-m10-ablation-robustness-design.md`
**Evidence version:** `m10-1.0.0` (`artifact_version` `1.0.0`)
**Tracked artifacts:** [`docs/modeling_artifacts/m10/1.0.0/`](modeling_artifacts/m10/1.0.0/)
**Manifest:** [`docs/modeling_artifacts/m10/1.0.0/manifest.json`](modeling_artifacts/m10/1.0.0/manifest.json)
**Approved feature set:** [`docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json`](modeling_artifacts/m10/1.0.0/approved_feature_set.json)

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
| `decision_worksheet.csv` | Evidence rows with human dispositions |
| `overall_metrics.csv` | Aggregate scores and Δ vs `market_only` |
| `fold_metrics.csv` | Per-fold paired Δs |
| `paired_bootstrap.csv` | Cluster bootstrap (n_boot=500) |
| `season_drop.csv` | Held-out season-drop aggregates (not retrains) |
| `anomalous_season.csv` | 2020 sensitivity (`not_available` here) |
| `calibration_summary.csv` | Diagnostic intercept/slope |
| `coverage_missingness.csv` | Coverage / missingness |
| `slice_metrics.csv` | Bounded robustness slices |
| `manifest.json` | SHA-256 of each artifact + source matrix + M10 code revision |
| `approved_feature_set.json` | Machine-readable promote / review_only / reject set |

Verify integrity by recomputing SHA-256 of each listed evidence file and matching
`manifest.json` (`source_matrix_sha256`, `m10_code_revision`,
`artifacts_sha256`). The approved-feature-set artifact separately records hashes
of the evidence manifest and completed worksheet.

## Corrections applied before this evidence version

1. Canonical matrix `true`/`false` Boolean predictors parse as numeric 1/0.
2. All-missing training features emit **no** transformed columns (marked
   unavailable) so the fit reproduces `market_only`.
3. Opening/movement fields (`spread_home_open`, `total_open`,
   `spread_move_home`, `total_move`) are **unavailable for evidence** and
   excluded from family variants and M11 eligibility.
4. Protocol bootstrap **n_boot=500**.

## Human dispositions

**Reviewer:** Matt Ryan
**Reviewed at (UTC):** `2026-09-04T21:20:02Z`
**Evidence version:** `m10-1.0.0`
**Outcome:** `no_features_promoted` (`promoted_features: []`)

### Rationale

- No feature or family demonstrated stable, material improvement over
  `market_only`.
- All family-level log-loss confidence intervals crossed zero.
- Evidence covers only held-out seasons 2022–2025; 2020 sensitivity was
  unavailable.
- `home_sos` showed the strongest individual directional result but remained
  uncertain.
- `market_context` improved aggregate proper scores but was inconsistent by
  season and uncertain.
- Accuracy was not used for promotion.
- Opening/movement fields remain **unavailable** (not converted to reject).
- Leave-family-out rows are context only (`not_applicable`), not promotable
  units.

### Decision table

<!-- m10-human-dispositions-begin -->
| unit_id | decision |
| --- | --- |
| single__home_field_advantage | reject |
| single__is_week_1 | reject |
| single__is_weeks_1_3 | reject |
| single__home_conference | reject |
| single__away_conference | reject |
| single__home_classification | reject |
| single__away_classification | reject |
| single__home_entering_wins | reject |
| single__home_entering_losses | reject |
| single__away_entering_wins | reject |
| single__away_entering_losses | reject |
| single__home_previous_result | reject |
| single__away_previous_result | reject |
| single__home_sos | review_only |
| single__away_sos | reject |
| single__home_days_rest | reject |
| single__away_days_rest | reject |
| single__spread_home | reject |
| single__total | reject |
| single__line_provider_count | reject |
| family__site_temporal | reject |
| family__history | reject |
| family__market_context | review_only |
| combined | reject |
| lof__without_site_temporal | not_applicable |
| lof__without_history | not_applicable |
| lof__without_market_context | not_applicable |
<!-- m10-human-dispositions-end -->

### Approved-feature-set summary

- **promoted_features:** none
- **review_only_features:** `home_sos`
- **review_only_families:** `market_context`
- **rejected_families:** `site_temporal`, `history`
- **rejected_units:** `combined`
- **unavailable_features:** `spread_home_open`, `total_open`, `spread_move_home`,
  `total_move`
- **M11:** blocked / fail-closed on empty `promoted_features` unless a future
  design explicitly permits baseline-only / no-challenger

## Rebuild (local; large outputs gitignored)

```bash
pick-prophet ablate-residual \
  --matrix data/processed/matrix/games_matrix_v1.csv \
  --protocol 1.0.0 \
  --out-dir artifacts/residual_ablation/run
```

Copy compact CSVs/JSON into a new versioned directory under
`docs/modeling_artifacts/m10/` and refresh `manifest.json` when regenerating.
Human dispositions and `approved_feature_set.json` are review artifacts, not
runner outputs.

## Hard rules

- Decision labels (`promote` / `review_only` / `reject` / `not_applicable`) are
  **human-only**.
- Do not auto-populate recommendations from the runner.
- M11 must fail closed when `promoted_features` is empty unless design
  explicitly permits a baseline-only / no-challenger outcome.
- Do not fall back to M08 `combined` when no features are promoted.
