# M17 point-in-time ratings decision

Status: **complete with timing/licensing stop condition**

## Outcome

No rating source is admitted to matrix schema 2.0.

- CFBD game-level pregame Elo and weekly Elo have substantial numeric coverage,
  but neither surface carries a historical publication timestamp. Numeric
  agreement does not prove consumer availability before kickoff.
- CFBD FPI and SP+ remain season-level in the available interface and cannot be
  used as weekly historical snapshots.
- SportsDataverse documents ESPN-derived power-index data and repository refresh
  timestamps, but those artifacts do not establish that each rating was
  published before the historical game. Its public weekly-FPI question remains
  unresolved.

Relevant source documentation:

- [SportsDataverse raw CFB repository](https://github.com/sportsdataverse/cfbfastR-cfb-raw)
- [SportsDataverse power-index schema](https://github.com/sportsdataverse/cfbfastR-cfb-data/blob/main/DATASETS.md)
- [Weekly FPI discussion](https://github.com/sportsdataverse/cfbfastR/discussions/105)

No ESPN-derived data was downloaded or redistributed, and no ambiguous license
was interpreted as permission.

## Future adapter gate

Every observation must carry stable team identity, rating name/value, source and
source version, effective time, publication time, and retrieval time. Publication
must be strictly before kickoff; retrieval time cannot substitute for it. Current
or end-of-season data and name-only identity joins are ineligible.

M20 must leave Elo/FPI/SP+ out of the model matrix. A later archive can reopen
this decision only with documented historical publication semantics and lawful
reproducibility.
