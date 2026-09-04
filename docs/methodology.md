# Evaluation methodology

## Research question

For every candidate signal, test both its standalone performance and its
incremental value over the market. The primary comparison is not coefficient
size; it is held-out predictive performance.

## Validation

Use expanding-window walk-forward validation by season. For test season `S`, fit
only on seasons `< S`. Hyperparameters must be selected inside the training
window. A single season cannot support this evaluation; 2025 validates the
pipeline, while meaningful backtesting requires several prior seasons.

## Models

- Market favorite and vig-removed moneyline probability.
- Univariate logistic models for spread, FPI differential, SP+ differential,
  poll-rank differential, and public/expert share.
- Market plus one signal, measuring change in held-out log loss and Brier score.
- A prespecified multivariable logistic model.
- Gradient boosting only after the simple baselines are stable.

Report accuracy, log loss, Brier score, sample size, missingness, and calibration
by probability bin. Bootstrap confidence intervals should resample by week, not
individual game, because games in a week share information and market regimes.

## Leakage controls

- Ratings and polls use their last publication strictly before kickoff.
- Entering records and previous result are computed with a shift within team and
  season; postseason is not allowed to contaminate regular-season rows.
- Closing odds are labelled as such. Earlier weekly recommendations use a model
  trained on equivalently timed snapshots or clearly disclose the mismatch.
- Feature selection decisions are made using training years only.
- The exact Pick'em slate is the sampling frame. Results on all FBS games are
  provisional and may not generalize to ESPN's curated slate.
