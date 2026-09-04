# Data coverage report

Generated: 2026-09-04T18:03:14.442482+00:00

Audits processed season CSVs under `data/processed/games_YYYY.csv`.
Seasons are never silently dropped: every discovered file appears below.

## Summary

| Season | Rows | Status | Completed | Odds | Elo | Joint | Neutral T/F | Market | Elo models | FPI |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| 2017 | 874 | pass | 874 | 873 | 829 | 829 | 63/811 | yes | yes | blocked_structural |
| 2018 | 884 | pass | 884 | 869 | 841 | 830 | 62/822 | yes | yes | blocked_structural |
| 2019 | 888 | pass | 888 | 881 | 849 | 843 | 59/829 | yes | yes | blocked_structural |
| 2020 | 570 | pass | 570 | 567 | 557 | 556 | 37/533 | yes | yes | blocked_structural |
| 2021 | 887 | pass | 887 | 887 | 848 | 848 | 59/828 | yes | yes | blocked_structural |
| 2022 | 896 | pass | 896 | 892 | 896 | 892 | 62/834 | yes | yes | blocked_structural |
| 2023 | 910 | pass | 910 | 907 | 910 | 907 | 63/847 | yes | yes | blocked_structural |
| 2024 | 920 | warn | 919 | 904 | 920 | 904 | 80/840 | yes | yes | blocked_structural |
| 2025 | 934 | pass | 934 | 934 | 933 | 933 | 64/870 | yes | yes | blocked_structural |

## Recommended evaluation windows

- Market baseline seasons: `[2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]`
- Elo model seasons: `[2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]`
- FPI model seasons: `[]` (expect empty until weekly archives)
- SP+ model seasons: `[]` (expect empty until weekly archives)
- Protocol 1.0.0 research seasons retained: `[2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]`
- Integrity-blocked seasons: `[]`

- FPI/SP+ remain structurally blocked until dated weekly archives exist.
- Thin-coverage seasons stay in the window but should be labelled in reports.
- Protocol 1.0.0 test seasons remain 2018–2025 regardless of thin coverage.

## Per-season checks

### 2017 (`data/processed/games_2017.csv`)

Overall status: **pass**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–15 (15 distinct)

- `unique_game_id` **pass**: 874 unique game_id values
- `outcome_consistency` **pass**: 874 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 873/874 rows have spread or implied prob (99.9%)
- `elo_coverage` **pass**: 829/874 rows have Elo (94.9%)
- `odds_rating_joint_coverage` **pass**: 829/874 rows have both odds and Elo (94.9%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=63 false=811
- `week_continuity` **pass**: weeks 1–15 present with no interior gaps
- `line_provider_coverage` **pass**: 874/874 rows have line_provider_count > 0 (100.0%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=290, coaches=289, CFP=85 (sparse ranks are structural for unranked teams)

### 2018 (`data/processed/games_2018.csv`)

Overall status: **pass**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–15 (15 distinct)

- `unique_game_id` **pass**: 884 unique game_id values
- `outcome_consistency` **pass**: 884 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 869/884 rows have spread or implied prob (98.3%)
- `elo_coverage` **pass**: 841/884 rows have Elo (95.1%)
- `odds_rating_joint_coverage` **pass**: 830/884 rows have both odds and Elo (93.9%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=62 false=822
- `week_continuity` **pass**: weeks 1–15 present with no interior gaps
- `line_provider_coverage` **pass**: 869/884 rows have line_provider_count > 0 (98.3%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=297, coaches=296, CFP=88 (sparse ranks are structural for unranked teams)

### 2019 (`data/processed/games_2019.csv`)

Overall status: **pass**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–15 (15 distinct)

- `unique_game_id` **pass**: 888 unique game_id values
- `outcome_consistency` **pass**: 888 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 881/888 rows have spread or implied prob (99.2%)
- `elo_coverage` **pass**: 849/888 rows have Elo (95.6%)
- `odds_rating_joint_coverage` **pass**: 843/888 rows have both odds and Elo (94.9%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=59 false=829
- `week_continuity` **pass**: weeks 1–15 present with no interior gaps
- `line_provider_coverage` **pass**: 881/888 rows have line_provider_count > 0 (99.2%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=297, coaches=296, CFP=71 (sparse ranks are structural for unranked teams)

### 2020 (`data/processed/games_2020.csv`)

Overall status: **pass**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–16 (16 distinct)

- `unique_game_id` **pass**: 570 unique game_id values
- `outcome_consistency` **pass**: 570 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 567/570 rows have spread or implied prob (99.5%)
- `elo_coverage` **pass**: 557/570 rows have Elo (97.7%)
- `odds_rating_joint_coverage` **pass**: 556/570 rows have both odds and Elo (97.5%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=37 false=533
- `week_continuity` **pass**: weeks 1–16 present with no interior gaps
- `line_provider_coverage` **pass**: 567/570 rows have line_provider_count > 0 (99.5%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=234, coaches=234, CFP=56 (sparse ranks are structural for unranked teams)

### 2021 (`data/processed/games_2021.csv`)

Overall status: **pass**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–15 (15 distinct)

- `unique_game_id` **pass**: 887 unique game_id values
- `outcome_consistency` **pass**: 887 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 887/887 rows have spread or implied prob (100.0%)
- `elo_coverage` **pass**: 848/887 rows have Elo (95.6%)
- `odds_rating_joint_coverage` **pass**: 848/887 rows have both odds and Elo (95.6%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=59 false=828
- `week_continuity` **pass**: weeks 1–15 present with no interior gaps
- `line_provider_coverage` **pass**: 887/887 rows have line_provider_count > 0 (100.0%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=302, coaches=302, CFP=88 (sparse ranks are structural for unranked teams)

### 2022 (`data/processed/games_2022.csv`)

Overall status: **pass**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–15 (15 distinct)

- `unique_game_id` **pass**: 896 unique game_id values
- `outcome_consistency` **pass**: 896 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 892/896 rows have spread or implied prob (99.6%)
- `elo_coverage` **pass**: 896/896 rows have Elo (100.0%)
- `odds_rating_joint_coverage` **pass**: 892/896 rows have both odds and Elo (99.6%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=62 false=834
- `week_continuity` **pass**: weeks 1–15 present with no interior gaps
- `line_provider_coverage` **pass**: 892/896 rows have line_provider_count > 0 (99.6%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=301, coaches=300, CFP=86 (sparse ranks are structural for unranked teams)

### 2023 (`data/processed/games_2023.csv`)

Overall status: **pass**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–15 (15 distinct)

- `unique_game_id` **pass**: 910 unique game_id values
- `outcome_consistency` **pass**: 910 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 907/910 rows have spread or implied prob (99.7%)
- `elo_coverage` **pass**: 910/910 rows have Elo (100.0%)
- `odds_rating_joint_coverage` **pass**: 907/910 rows have both odds and Elo (99.7%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=63 false=847
- `week_continuity` **pass**: weeks 1–15 present with no interior gaps
- `line_provider_coverage` **pass**: 907/910 rows have line_provider_count > 0 (99.7%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=294, coaches=294, CFP=111 (sparse ranks are structural for unranked teams)

### 2024 (`data/processed/games_2024.csv`)

Overall status: **warn**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–16 (16 distinct)

- `unique_game_id` **pass**: 920 unique game_id values
- `outcome_consistency` **pass**: 919 completed games with consistent outcomes
- `completed_outcomes` **warn**: 1 rows missing final scores
- `odds_coverage` **pass**: 904/920 rows have spread or implied prob (98.3%)
- `elo_coverage` **pass**: 920/920 rows have Elo (100.0%)
- `odds_rating_joint_coverage` **pass**: 904/920 rows have both odds and Elo (98.3%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=80 false=840
- `week_continuity` **pass**: weeks 1–16 present with no interior gaps
- `line_provider_coverage` **pass**: 904/920 rows have line_provider_count > 0 (98.3%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=301, coaches=301, CFP=81 (sparse ranks are structural for unranked teams)

### 2025 (`data/processed/games_2025.csv`)

Overall status: **pass**

Usable for: `{'market_baseline': 'yes', 'elo_models': 'yes', 'fpi_models': 'blocked_structural', 'sp_models': 'blocked_structural', 'rank_features': 'yes_with_missing_indicators', 'protocol_1_0_0_fold': 'yes'}`

Weeks covered: 1–16 (16 distinct)

- `unique_game_id` **pass**: 934 unique game_id values
- `outcome_consistency` **pass**: 934 completed games with consistent outcomes
- `completed_outcomes` **pass**: all rows have final scores
- `odds_coverage` **pass**: 934/934 rows have spread or implied prob (100.0%)
- `elo_coverage` **pass**: 933/934 rows have Elo (99.9%)
- `odds_rating_joint_coverage` **pass**: 933/934 rows have both odds and Elo (99.9%)
- `team_identity` **pass**: all rows have home/away team names and IDs
- `neutral_site` **pass**: neutral_site true=64 false=870
- `week_continuity` **pass**: weeks 1–16 present with no interior gaps
- `line_provider_coverage` **pass**: 934/934 rows have line_provider_count > 0 (100.0%)
- `fpi_missingness` **pass**: FPI columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `sp_missingness` **pass**: SP+ columns are entirely null (season-level CFBD pulls deliberately unjoined until dated weekly archives exist)
- `rank_coverage` **pass**: AP non-null cells=298, coaches=298, CFP=78 (sparse ranks are structural for unranked teams)

## Gate

Cross-season gate: **warn**

Fail means at least one season has a blocking integrity issue (duplicate IDs, broken outcomes, missing identities, or empty file).
Warn means coverage is thin but the season remains in the window.
