# Data coverage report

Generated: 2026-09-04T17:11:14.229207+00:00

Audits processed season CSVs under `data/processed/games_YYYY.csv`.
Seasons are never silently dropped: every discovered file appears below.

## Summary

| Season | Rows | Status | Completed | Odds | Elo | Joint | Neutral T/F |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 2017 | 874 | pass | 874 | 873 | 829 | 829 | 63/811 |
| 2018 | 884 | pass | 884 | 869 | 841 | 830 | 62/822 |
| 2019 | 888 | pass | 888 | 881 | 849 | 843 | 59/829 |
| 2020 | 570 | pass | 570 | 567 | 557 | 556 | 37/533 |
| 2021 | 887 | pass | 887 | 887 | 848 | 848 | 59/828 |
| 2022 | 896 | pass | 896 | 892 | 896 | 892 | 62/834 |
| 2023 | 910 | pass | 910 | 907 | 910 | 907 | 63/847 |
| 2024 | 920 | warn | 919 | 904 | 920 | 904 | 80/840 |
| 2025 | 934 | pass | 934 | 934 | 933 | 933 | 64/870 |

## Per-season checks

### 2017 (`data/processed/games_2017.csv`)

Overall status: **pass**

- `unique_game_id` **pass**: 874 unique game_id values
- `outcome_consistency` **pass**: 874 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 873/874 rows have spread or implied prob (99.9%)
- `elo_coverage` **pass**: 829/874 rows have Elo (94.9%)
- `odds_rating_joint_coverage` **pass**: 829/874 rows have both odds and Elo (94.9%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=63 false=811

### 2018 (`data/processed/games_2018.csv`)

Overall status: **pass**

- `unique_game_id` **pass**: 884 unique game_id values
- `outcome_consistency` **pass**: 884 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 869/884 rows have spread or implied prob (98.3%)
- `elo_coverage` **pass**: 841/884 rows have Elo (95.1%)
- `odds_rating_joint_coverage` **pass**: 830/884 rows have both odds and Elo (93.9%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=62 false=822

### 2019 (`data/processed/games_2019.csv`)

Overall status: **pass**

- `unique_game_id` **pass**: 888 unique game_id values
- `outcome_consistency` **pass**: 888 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 881/888 rows have spread or implied prob (99.2%)
- `elo_coverage` **pass**: 849/888 rows have Elo (95.6%)
- `odds_rating_joint_coverage` **pass**: 843/888 rows have both odds and Elo (94.9%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=59 false=829

### 2020 (`data/processed/games_2020.csv`)

Overall status: **pass**

- `unique_game_id` **pass**: 570 unique game_id values
- `outcome_consistency` **pass**: 570 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 567/570 rows have spread or implied prob (99.5%)
- `elo_coverage` **pass**: 557/570 rows have Elo (97.7%)
- `odds_rating_joint_coverage` **pass**: 556/570 rows have both odds and Elo (97.5%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=37 false=533

### 2021 (`data/processed/games_2021.csv`)

Overall status: **pass**

- `unique_game_id` **pass**: 887 unique game_id values
- `outcome_consistency` **pass**: 887 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 887/887 rows have spread or implied prob (100.0%)
- `elo_coverage` **pass**: 848/887 rows have Elo (95.6%)
- `odds_rating_joint_coverage` **pass**: 848/887 rows have both odds and Elo (95.6%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=59 false=828

### 2022 (`data/processed/games_2022.csv`)

Overall status: **pass**

- `unique_game_id` **pass**: 896 unique game_id values
- `outcome_consistency` **pass**: 896 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 892/896 rows have spread or implied prob (99.6%)
- `elo_coverage` **pass**: 896/896 rows have Elo (100.0%)
- `odds_rating_joint_coverage` **pass**: 892/896 rows have both odds and Elo (99.6%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=62 false=834

### 2023 (`data/processed/games_2023.csv`)

Overall status: **pass**

- `unique_game_id` **pass**: 910 unique game_id values
- `outcome_consistency` **pass**: 910 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 907/910 rows have spread or implied prob (99.7%)
- `elo_coverage` **pass**: 910/910 rows have Elo (100.0%)
- `odds_rating_joint_coverage` **pass**: 907/910 rows have both odds and Elo (99.7%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=63 false=847

### 2024 (`data/processed/games_2024.csv`)

Overall status: **warn**

- `unique_game_id` **pass**: 920 unique game_id values
- `outcome_consistency` **pass**: 919 completed games with consistent outcomes
- `completed_outcomes` **warn**: 1 rows missing final scores
- `odds_coverage` **pass**: 904/920 rows have spread or implied prob (98.3%)
- `elo_coverage` **pass**: 920/920 rows have Elo (100.0%)
- `odds_rating_joint_coverage` **pass**: 904/920 rows have both odds and Elo (98.3%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=80 false=840

### 2025 (`data/processed/games_2025.csv`)

Overall status: **pass**

- `unique_game_id` **pass**: 934 unique game_id values
- `outcome_consistency` **pass**: 934 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 934/934 rows have spread or implied prob (100.0%)
- `elo_coverage` **pass**: 933/934 rows have Elo (99.9%)
- `odds_rating_joint_coverage` **pass**: 933/934 rows have both odds and Elo (99.9%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=64 false=870

## Gate

Cross-season gate: **warn**

Fail means at least one season has a blocking integrity issue (duplicate IDs, broken outcomes, missing identities, or empty file).
Warn means coverage is thin but the season remains in the window.
