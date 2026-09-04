# M15 verified ESPN Pick'em history expansion design

Date: 2026-09-04
Status: implemented with stop condition
Branch: `codex/m15-espn-history-expansion`

## Contract

M15 may add a historical week to `verified_espn_pickem` only when matchup rows
are supported by at least two distinct verifiers, have pre-lock provenance, and
resolve to canonical game IDs. Search results, generic schedules, inferred
prominence, and a single prediction article cannot confirm membership.

## Result

Two dated 2024 article candidates were found. Neither has independent
verification or a preserved ESPN row-level page, so zero weeks are imported.
The candidates are retained as URL-level research leads only. No page contents
are copied or used as model data.

This is the roadmap's valid source-feasibility stop condition. M15 completes
without weakening the sampling-frame definition, and M20 must retain the
all-FBS/verified-ESPN separation.
