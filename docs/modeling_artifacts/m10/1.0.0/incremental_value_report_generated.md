# Incremental value report (M10)

**INFERENCE WINDOW: residual ablation proper-score evidence covers held-out seasons 2022–2025 only (moneyline/implied coverage; earlier expanding folds skipped when train/test eligible sets are empty). 2020 anomalous-season sensitivity cannot be evaluated in this pull (no eligible held-out predictions for 2020).**

Evidence from the M08 fixed-offset residual ablation runner.
Large row-level fit artifacts are not committed; see compact CSVs.

- Bootstrap: n_boot=500 (protocol), seed=20260904
- Structurally unavailable (excluded from evidence/M11 eligibility): spread_home_open, spread_move_home, total_move, total_open

## Hard rules

- Comparisons reuse M08 fitting; no new model family or HP search.
- Season-drop rows are **aggregations of existing held-out predictions**, not retrains.
- Decision labels (`promote` / `review_only` / `reject`) are **human-only**;
  `decision_worksheet.csv` leaves `recommendation` unset.
- Do not treat an unavailable anomalous season as a successful exclusion contrast.

## Aggregate deltas vs market_only

- `single__home_field_advantage`: n=3195, Δlog_loss=3.378459480507523e-06, Δbrier=6.036648314361459e-06
- `single__is_week_1`: n=3195, Δlog_loss=7.948123141665597e-05, Δbrier=3.103275914684289e-05
- `single__is_weeks_1_3`: n=3195, Δlog_loss=5.594016693577508e-05, Δbrier=2.5316993337409777e-05
- `single__home_conference`: n=3195, Δlog_loss=-1.9759541459718477e-06, Δbrier=2.5938239215650416e-06
- `single__away_conference`: n=3195, Δlog_loss=7.905526980156452e-06, Δbrier=-1.4545013866662515e-06
- `single__home_classification`: n=3195, Δlog_loss=0.0, Δbrier=0.0
- `single__away_classification`: n=3195, Δlog_loss=-1.464948672258437e-06, Δbrier=-2.712004049942873e-07
- `single__home_entering_wins`: n=3195, Δlog_loss=0.00011437489627330599, Δbrier=4.748214989638844e-05
- `single__home_entering_losses`: n=3195, Δlog_loss=-8.03533926984068e-05, Δbrier=-2.6233505475509178e-05
- `single__away_entering_wins`: n=3195, Δlog_loss=4.072184236481036e-06, Δbrier=7.277774582259422e-06
- `single__away_entering_losses`: n=3195, Δlog_loss=8.10073321644289e-05, Δbrier=3.1373427497982664e-05
- `single__home_previous_result`: n=3195, Δlog_loss=-3.4049146749426384e-05, Δbrier=-1.39624330385002e-05
- `single__away_previous_result`: n=3195, Δlog_loss=3.5121869672027906e-05, Δbrier=9.593788662221048e-06
- `single__home_sos`: n=3195, Δlog_loss=-0.0002223894274129279, Δbrier=-0.00010031797820844734
- `single__away_sos`: n=3195, Δlog_loss=3.4273530310491296e-05, Δbrier=1.2553747079091515e-05
- `single__home_days_rest`: n=3195, Δlog_loss=4.9009315765458084e-05, Δbrier=1.573300116780585e-05
- `single__away_days_rest`: n=3195, Δlog_loss=4.404207787478409e-05, Δbrier=1.281606078273878e-05
- `single__spread_home`: n=3195, Δlog_loss=-1.2988085522747106e-05, Δbrier=1.3575934831866476e-06
- `single__total`: n=3195, Δlog_loss=-1.5778178349412642e-06, Δbrier=-4.61720804106891e-06
- `single__line_provider_count`: n=3195, Δlog_loss=-4.523456248728408e-05, Δbrier=-1.2632273639096026e-05
- `family__site_temporal`: n=3195, Δlog_loss=0.00012948301319615219, Δbrier=5.842114022258649e-05
- `family__history`: n=3195, Δlog_loss=5.0541884528243486e-05, Δbrier=4.576950123902357e-07
- `family__market_context`: n=3195, Δlog_loss=-6.729678181693899e-05, Δbrier=-1.8602232708359034e-05
- `combined`: n=3195, Δlog_loss=9.102549721362596e-05, Δbrier=3.145197729370608e-05
- `lof__without_site_temporal`: n=3195, Δlog_loss=-1.538576709547712e-05, Δbrier=-1.8325660649798348e-05
- `lof__without_history`: n=3195, Δlog_loss=6.5954399660062e-05, Δbrier=4.145041338554645e-05
- `lof__without_market_context`: n=3195, Δlog_loss=0.0001515444614526018, Δbrier=4.788617097259418e-05

## Human review

Fill `recommendation` in `decision_worksheet.csv` after reviewing
fold consistency, bootstrap CIs, calibration, missingness, season-drop,
and anomalous-season (2020) tables. Do not treat accuracy alone as promotion evidence.
