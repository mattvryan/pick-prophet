# M15 ESPN Pick'em history expansion

Status: **complete — no dual-verified historical weeks added**
Protocol: `2.0.0`

## Outcome

The public-source pass found dated third-party articles that enumerate the ten
ESPN College Pick'em matchups for 2024 Weeks 3 and 12. They are useful candidate
evidence, but neither week has a second independent source or a preserved ESPN
row-level artifact. They therefore remain `candidate_single_source` and do not
enter `verified_espn_pickem`.

ESPN's ended [2022 game page](https://fantasy.espn.com/games/college-football-pickem-2022/)
and [2024 game page](https://fantasy.espn.com/games/college-football-pickem-2024/)
retain contest-level metadata but do not expose historical weekly matchup rows
in their public rendered pages. The dated RotoBaller candidate articles are:

- [2024 Week 3](https://www.rotoballer.com/college-football-pick-em-pool-picks-week-3-2024-targets-avoids-predictions-for-espn-pick-em-contests/1439887)
- [2024 Week 12](https://www.rotoballer.com/college-football-pick-em-pool-picks-week-12-2024-targets-avoids-predictions-for-espn-pick-em-contests/1493024)

No article text or copyrighted page snapshot is redistributed. The compact
inventory stores URLs, dates, provenance classification, and verification
status only.

## Decision

- Historical verified ESPN frame remains unavailable and underpowered.
- M20 must not infer ESPN membership or use the two candidate weeks.
- All-FBS remains the historical modeling frame, explicitly provisional for
  contest generalization.
- Forward weekly capture remains the best path to a genuine prospective ESPN
  frame.
- If the user later supplies historical screenshots/exports, import them through
  the existing M05 contract and require a second verifier before confirmation.

## Reproducibility and integrity

Machine-readable inventory:
`docs/modeling_artifacts/m15/1.0.0/source_inventory.json`.
`validate_source_inventory` fails closed if a week is labelled confirmed without
two distinct source IDs, pre-lock provenance, and canonical game IDs.
