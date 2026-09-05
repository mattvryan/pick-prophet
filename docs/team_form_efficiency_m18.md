# M18 point-in-time team form and efficiency

Status: **source and feature gate passed; evaluation deferred to M20**

## Outcome

CFBD's game-level advanced-stat endpoint produced 20,616 team-game rows for
2017–2025. Those observations reconcile by stable CFBD game ID and exact team
identity to the canonical matrix. The resulting compact form family is complete
for 6,552 of 7,763 games (84.4%). Annual coverage is stable at 83.3%–85.3%,
including the anomalous 2020 season; no outcome was inspected to make the source
or feature decision.

The admitted candidates are home-minus-away differentials for rolling:

- offensive and defensive PPA;
- offensive and defensive success rate; and
- offensive and defensive explosiveness.

Every value is computed from completed games earlier in the same season. The
current game is added only after its pregame feature row is emitted. Each
observation is centered on the opponent's prior rolling counterpart, with a
fixed zero center when the opponent has no history. `prior_games_home` and
`prior_games_away` expose sample depth. Week 1 remains missing rather than being
silently assigned a preseason prior.

## Reproduction and temporal rules

The local immutable snapshots came from CFBD
[`/stats/game/advanced`](https://apinext.collegefootballdata.com/). The research
frame can be rebuilt with:

```bash
python -m pick_prophet.research.m18_team_form \
  --games data/processed/matrix/games_matrix_v1.csv \
  --snapshots data/raw/m18_advanced \
  --output data/processed/m18/team_form_features.csv
```

The raw cache and generated feature CSV are intentionally gitignored; source
hashes, retrieval times, coverage, and the generated-frame hash are preserved in
`docs/modeling_artifacts/m18/1.0.0/`.

Although the source payloads were retrieved later, they contain final statistics
for completed games. They are eligible only as lagged observations: a future or
current game can never affect an earlier pregame row. This is different from a
historical rating, whose publication time would itself need proof.

## M20 gate

Passing M18 makes the family eligible for the predeclared incremental-value
study; it does not promote any feature. M20 must use identical held-out IDs and
the frozen market baseline, nest all learned preprocessing inside training
folds, report missingness and season stability, and obtain human dispositions.
The 2026 prospective outcomes remain locked.
