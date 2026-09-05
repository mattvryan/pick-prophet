# M21 no-challenger close-out design

Date: 2026-09-04
Status: complete; no challenger trained
Branch: `codex/m21-no-challenger-closeout`

M20 produced no variant eligible for human promotion review. Matt Ryan approved
the evidence-consistent `no_features_promoted` disposition. The versioned M20
approved-feature-set artifact records an empty promote set, all rejected units,
the exploratory offensive-explosiveness lead, reviewer, timestamp, and hashes of
the immutable prereview evidence.

M21 hash-checks that approved artifact and fails closed unless its status is
`no_features_promoted` and `promoted_features` is empty. Consequently, M21 does
not refit the residual model, train a nonlinear challenger, calibrate candidate
probabilities, create a bundle, change the registry, or run a new weekly shadow
model. The existing approved `market_only` registry entry remains authoritative.

Reopening requires a new frozen protocol and evidence cycle that results in an
explicit human promotion of at least one feature. The current exploratory lead
cannot enter a model without that prospective declaration and evaluation. No
2026 outcome was used.
