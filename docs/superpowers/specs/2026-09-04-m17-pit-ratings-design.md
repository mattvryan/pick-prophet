# M17 PIT ratings design

Date: 2026-09-04
Status: complete with stop condition
Branch: `codex/m17-pit-ratings`

M17 reopens the M06 source review under protocol 2.0. An adapter requires
historical publication time, stable IDs, lawful reproducibility, and adequate
weekly coverage. Effective/computation time and repository retrieval/refresh
time are recorded separately and cannot stand in for publication time.

No reviewed source clears all gates, so the correct output is an immutable omit
decision plus a tested future observation validator. Production ingestion,
matrix joins, and weekly scoring remain unchanged.
