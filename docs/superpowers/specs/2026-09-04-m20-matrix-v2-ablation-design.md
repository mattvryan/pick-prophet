# M20 matrix 2.0 and incremental-value study design

Date: 2026-09-04
Status: complete; awaiting human disposition
Branch: `codex/m20-matrix-v2-ablation`

Matrix schema 2.0 joins the canonical 2017–2025 matrix to the M18 team-form
and M19 season-opening coaching frames by exact game ID and season. Any missing,
duplicate, extra, mismatched, or 2026 row fails closed. Targets and the fixed
market offset retain their existing roles. Candidate, audit, and sampling-frame
roles are explicit in the committed schema artifact.

The predeclared variants are market-only; eight single-feature additions; two
family additions; one combined residual model; and two leave-family-out models.
All candidates use the fixed market logit as an offset. Numeric imputation,
missingness indicators, centering, scaling, and L2 fitting occur within each
expanding training fold. Test seasons are never used to estimate preprocessing
or model parameters.

Confirmatory inference is restricted to the identical 3,195 market-eligible
games in held-out seasons 2022–2025. Proper-score deltas are candidate minus
market. Confidence intervals and p-values use 2,000 deterministic bootstrap
resamples clustered by `(test_season, season_type, week)`. Holm adjustment is
applied within each family to single-feature tests separately for log loss and
Brier score. The frozen protocol 2.0 gates determine only eligibility for human
review; automated code cannot promote, reject, or approve a feature.

The compact output contains overall uncertainty, season stability, all gate
results, and an empty human-disposition record. Detailed fits and predictions
are reproducible local artifacts and are not committed. No 2026 outcome enters
the matrix or study.
