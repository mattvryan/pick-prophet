# M19 preseason personnel and program context

Status: **coaching source gate passed; other candidate families omitted**

## Admitted candidate

CFBD's historical coaches surface returned 1,816 stable coach records containing
12,564 coach-team-season assignments. The season-opening coaching context is
known for both teams in 6,729 of 7,763 canonical games (86.7%) from 2017–2025.
Annual completeness ranges from 81.4% to 93.7%; unknowns remain explicit.

The two predeclared model candidates are:

- home-minus-away season-opening head-coach tenure at the school; and
- home-minus-away first-year head-coach status.

The API's `hireDate` belongs to the coach's career and is not a school-tenure
date, so the implementation deliberately does not use it. Tenure is derived
from the first observed season for the same stable coach/team ID pair. A sole
coach continuing from the prior team-season resolves the opening coach when a
later in-season replacement creates multiple assignments. Other multi-coach
cases are unknown; the system does not invent a change date.

M20 may use fold-nested imputation with an explicit knownness indicator so that
unknown does not mean no change. Passing this gate does not establish predictive
value or authorize production use.

## Omitted candidates

| Family | M19 decision | Reason |
|---|---|---|
| Returning production | Omit | CFBD provides historical values, but no observation-level publication time was established. |
| Team talent | Omit | Annual values are available, but historical preseason availability/revision timing is unproven. |
| Returning/changed QB | Omit | No stable, dated cross-season role and prior-start history source was established. |
| Coordinator continuity | Omit | The reviewed coach surface identifies head coaches, not consistently dated coordinator assignments. |
| Preseason ratings | Omit | M17's publication-time stop condition still applies. |
| Rivalry registry | Omit | No versioned curated mapping and definition has been approved. |
| Travel/venue | Omit | Venue coordinates may be reproducible, but travel-party origin and a predeclared incremental hypothesis are absent; existing rest features were not promoted. |

## Reproduction

The immutable source payload is captured from CFBD `/coaches`; the generated
CSV is rebuilt with:

```bash
python -m pick_prophet.research.m19_coaching_context \
  --games data/processed/matrix/games_matrix_v1.csv \
  --coaches data/raw/m19_coaches/<capture>/coaches.json \
  --output data/processed/m19/coaching_features.csv
```

Raw and generated data stay gitignored. Compact source hashes and coverage are
committed under `docs/modeling_artifacts/m19/1.0.0/`. No 2026 outcome was used.
