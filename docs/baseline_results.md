# Historical baseline results

Run date: 2026-09-04
Dataset: CFBD 2017–2025
Sampling frame: all completed games involving at least one FBS team, not the
confirmed historical ESPN Pick'em slate

## Dataset and coverage

- 7,762 completed games across nine seasons.
- Point-spread coverage is at least 98.3% in every season.
- Two-way moneylines are unavailable before 2021 in this pull; coverage rises
  from 79.7% in 2022 to 92.5% in 2025.
- Pregame Elo differential coverage is 73.5%–77.6% by season.
- Historical FPI and SP+ are deliberately null: CFBD's current season-level
  endpoints cannot establish which value was available before each old game.

## Direct market baselines

| Baseline | Rows | Accuracy | Log loss | Brier |
|---|---:|---:|---:|---:|
| Spread favorite, 2017–2025 | 7,701 | 75.90% | — | — |
| Vig-removed moneyline, 2021–2025 | 3,933 | 71.83% | 0.5353 | 0.1806 |

The accuracy figures are **not directly comparable** because moneylines cover a
different and likely more competitive subset. On the 3,928 rows having both a
nonzero spread and a two-way moneyline, the spread favorite was correct 72.40%,
which is much closer to the moneyline selection accuracy.

## Expanding-window walk-forward models

For test season `S`, each model was fitted only on seasons earlier than `S`.
Metrics below are row-weighted across the 2018–2025 test folds.

| Model | Test folds | Test rows | Accuracy | Log loss | Brier |
|---|---:|---:|---:|---:|---:|
| Spread logistic | 8 | 6,841 | 75.81% | 0.4750 | 0.1586 |
| Pregame Elo logistic | 8 | 5,192 | 71.86% | 0.5454 | 0.1844 |
| Spread + Elo logistic | 8 | 5,192 | 73.40% | 0.5176 | 0.1735 |

The combined model and spread-only aggregate above use different row sets, so
this table does not yet prove whether Elo adds or destroys market information.
That requires a paired evaluation in which both models train and score on the
same complete rows. It is the next statistical experiment.

## What is safe to conclude

- The market is the strongest established baseline so far.
- Elo is predictive by itself but cannot yet be claimed to add information after
  controlling for the spread.
- Overall FBS accuracy overstates expected ESPN performance because the full
  schedule includes large mismatches; ESPN curates a harder slate.
- Public-pick percentages cannot be backtested until the historical ESPN sampling
  frame is recovered.
- Historical CFBD line observations lack provider timestamps. They are treated as
  final/closing-like values, not as proof of exactly what was available at an
  earlier weekly decision time.

## Reproduction

```bash
pick-prophet analyze --input data/processed/games_2017_2025.csv
```

Machine-readable results are written to
`data/processed/games_2017_2025.analysis.json`.
