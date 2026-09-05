# M18 team-form efficiency design

Date: 2026-09-04
Status: complete; candidate family admitted to M20 evaluation
Branch: `codex/m18-team-form-efficiency`

M18 captures CFBD game-level advanced statistics and derives a compact,
chronological feature family. Final game statistics are observations of a
completed game, not contemporaneous ratings: retrieval may occur later, but an
observation may update team history only after that game's kickoff-ordered
pregame row has been emitted.

The family contains home-minus-away rolling differentials for offense and
defense PPA, success rate, and explosiveness. Each team-game observation is
centered on the opponent's prior rolling counterpart. The calculation is online,
season-local, and uses a fixed zero center before an opponent has history; it
does not estimate a parameter from held-out rows. Preseason priors, cross-season
carryover, targets, and 2026 outcomes are excluded.

Rows remain missing until both teams have a prior captured game. Missingness is
not imputed here. M20 must perform any imputation, scaling, shrinkage, or feature
selection within each training fold and must evaluate this family under protocol
2.0.0 before a human disposition.

The adapter preserves immutable source payloads and manifests locally. Schema,
duplicate team/game identities, multiple captures for the same season, and team
identity mismatches fail closed. Future-game mutation and current-game cutoff
tests enforce chronology. Production weekly scoring is unchanged.
