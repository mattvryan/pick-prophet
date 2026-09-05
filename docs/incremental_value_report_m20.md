# M20 incremental-value report

Status: **study complete; human disposition required**

## Result

No M18 or M19 candidate clears protocol 2.0's promotion-eligibility gates. The
market-only model remains the evidence-backed baseline.

All 13 candidate variants produced predictions for the same 3,195 held-out
games across 2022–2025. Sample-size, paired-coverage, and calibration gates pass,
but no variant has both proper-score confidence intervals strictly below zero.
No Holm-adjusted single-feature test rejects its null.

| Variant | Δ log loss | 95% CI | Δ Brier | 95% CI | Eligible |
|---|---:|---:|---:|---:|---|
| Team-form family | +0.000039 | [-0.000175, +0.000250] | +0.000029 | [-0.000056, +0.000115] | No |
| Coaching family | +0.000078 | [-0.000053, +0.000204] | +0.000045 | [-0.000011, +0.000101] | No |
| Combined | +0.000117 | [-0.000137, +0.000365] | +0.000074 | [-0.000036, +0.000179] | No |

Positive deltas mean worse than market. Offensive explosiveness is the only
single feature with negative aggregate deltas for both scores and non-positive
log-loss deltas in all four seasons. Its effect is very small (Δ log loss
-0.000054; Δ Brier -0.000015), both confidence intervals cross zero, and neither
materiality threshold is met. It is therefore not eligible in this cycle; it
may be a predeclared exploratory lead for a later protocol, not a promoted
feature now.

## Interpretation

The study does not show that on-field form or coaching never matters. It shows
that these exact reproducible transformations do not demonstrate stable,
independent value beyond the available vig-free market probability at the
current sample size. The family and combined estimates are directionally worse,
and season-level effects are unstable.

Feature-source completeness on the inference rows is 91.5% for team form and
93.7% for coaching. Both complete-source family slices are directionally worse
than market. The smaller missing-source slices do not rescue the aggregate
result and are descriptive only. Across expanding folds, four of six raw
team-form coefficients, one of two raw coaching coefficients, and five of eight
combined raw coefficients retain their sign; this partial stability is
insufficient given the proper-score results. Full transformed-coefficient and
missingness tables are committed with the packet.

The verified ESPN Pick'em population remains unavailable, so this is an all-FBS
inference result. The 2026 prospective stream remains sealed.

## Required human decision

Automated eligibility is empty. A human must explicitly record either
`no_features_promoted` (consistent with the frozen gates) or a protocol-level
exception with rationale. M21 stays blocked unless a nonempty feature set is
human-promoted. An exception would not be justified by the confirmatory evidence
in this packet.

Detailed values are in `docs/modeling_artifacts/m20/2.0.0/variant_summary.csv`
and `season_stability.csv`; robustness is in `coefficient_stability.csv` and
`missingness_sensitivity.csv`. The decision packet intentionally contains no
human dispositions.
