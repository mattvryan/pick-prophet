# M19 preseason personnel and program context design

Date: 2026-09-04
Status: complete; coaching family admitted, other families omitted
Branch: `codex/m19-program-context`

M19 evaluates candidate context sources before modeling. A family requires
stable identity, a definition that can be reproduced across seasons, and an
effective-time interpretation that does not depend on later outcomes.

CFBD head-coach history clears that gate for season-opening continuity. Coach
and team IDs are stable, and full career season rows permit school-specific
tenure to be derived without using the misleading coach-level `hireDate`. A
unique team-season coach is accepted. When a season contains multiple coaches,
only a sole coach also attributed to the prior team-season is accepted as the
season opener; all other cases remain unknown because team-specific change dates
are absent. The features are opening-coach tenure difference and first-year
status difference.

M20 may median-impute tenure and zero-impute first-year difference only inside
each training fold, with an explicit `coaching_context_known` indicator. Raw
unknowns must remain distinguishable in matrix 2.0. This gate admits a candidate
to evaluation and is not a promotion.

Returning production, talent, quarterback continuity, coordinator continuity,
archived preseason ratings, rivalry, and travel are omitted in this PR. The
available numerical returning-production and talent endpoints do not prove when
each historical value was published. The other families lack a stable, dated,
reproducible source or registry. No proxy substitution is allowed.
