# Early-season evaluation

Run date: 2026-09-04
Input: CFBD 2017–2025 games involving at least one FBS team
Design: expanding-window season validation with spread-only and spread-plus-Elo
models fitted and scored on identical complete rows within each time slice

## Results

| Slice | Test folds | Games | Model | Accuracy | Log loss | Brier |
|---|---:|---:|---|---:|---:|---:|
| Week 1 | 8 | 658 | Spread | 71.73% | 0.5347 | 0.1826 |
| Week 1 | 8 | 658 | Spread + pregame Elo | 71.43% | 0.5392 | 0.1844 |
| Weeks 1–3 | 8 | 1,372 | Spread | 73.25% | 0.5052 | 0.1716 |
| Weeks 1–3 | 8 | 1,372 | Spread + pregame Elo | 72.16% | 0.5068 | 0.1722 |
| Week 4+ | 8 | 4,662 | Spread | 73.17% | 0.5234 | 0.1754 |
| Week 4+ | 8 | 4,662 | Spread + pregame Elo | 73.12% | 0.5238 | 0.1756 |

For Week 1, adding Elo worsened log loss by 0.0045 and Brier score by 0.0017;
lower is better. It improved those scores in only two of eight held-out seasons.
Across Weeks 1–3 it also slightly worsened both proper scoring rules and reduced
accuracy by 1.09 percentage points.

## Operational decision for the current slate

- Use the market as the quantitative baseline.
- Do not blend Elo into the probability merely because it is available.
- Treat FPI, SP+, and Elo disagreement as a review trigger, not an automatic
  override, until they demonstrate paired held-out value beyond the market.
- Early-season roster/coaching/QB context may identify information absent from an
  old line, but a current market refresh is the first response to such news.
- Any qualitative departure from the market must be documented separately and
  must not rewrite the baseline probability.

This conclusion is provisional for ESPN Pick'em: the historical sample is the
full FBS-involving schedule rather than ESPN's selected games. Still, the paired
result gives no empirical basis for adding Elo to this week's model.

## Reproduction

```bash
pick-prophet analyze-early-season \
  --input data/processed/games_2017_2025.csv
```

The command writes a JSON summary and row-level fold predictions. The saved
predictions make later confidence intervals and error analysis reproducible.
