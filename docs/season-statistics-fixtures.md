# Season statistics regression fixtures

`players/tests/fixtures/season_stats.json` contains synthetic, API-shaped inputs
and expected table values for the move to season-specific statistics. It contains
no database exports or live NHL responses. The `season_stats_data` pytest fixture
loads a fresh copy for each test; helpers that mutate their inputs should receive
an additional deep copy when the original response is needed for comparison.

Run the focused tests from the project root with the virtual environment active:

```bash
python -m pytest -c players/tests/pytest.ini players/tests/unit/other/tests_season_stats_fixtures.py
```

These tests use the existing season parser, average calculator, and mocked
stats/rest responses. They require neither a database connection nor network
access. They do not exercise page queries. The shared reader has a separate suite
in `players/tests/unit/other/tests_season_stats_reader.py`, using the same fixtures;
see [its contract](season-statistics-reader.md).

## Scenarios and expected table behavior

The requested season is fixed at `20262027`, displayed as `2026-27`; tests do not
depend on today's date or season autodetection. `landing_season_totals` uses the
shape of the landing endpoint's `seasonTotals` array. `snapshot` is a deliberately
partial set of ordinary player columns, not a complete model creation payload.
`expected` uses the existing table's field names. Missing keys in an expected
dictionary are outside that scenario's assertions, not implicit zero values.

| Case | Input distinction | Expected season-specific table behavior |
| --- | --- | --- |
| `old_season_only` | 2025-26 row with 80 games and 20 goals; no 2026-27 row | No current-season statistics; preserve the historical player and row. |
| `current_skater` | Historical and current rows, plus playoff and AHL distractors; snapshot still says 20 goals | Current regular NHL season has 10 games, 2 goals, 3 assists, 5 points; averages are 0.2, 0.3, 0.5. |
| `traded_skater` | COL: 4 games, 1 goal, 2 assists; BUF: 6 games, 3 goals, 3 assists | Players table: 10 games, 4 goals, 5 assists, 9 points; team tables retain separate contributions. |
| `current_goalie` | Current landing row differs from previous snapshot; saves absent from response | 4 games, 2 wins, 1 loss, 1 OT loss, 90 saves, GAA 2.5, save percentage 0.9, 0 shutouts. |
| `missing_enrichment` | Some fields omitted, blocks explicitly null, empty report responses, stale snapshot values | Preserve genuine zero goals; unknown hits, blocks, faceoffs and special-teams TOI stay unavailable. |

The current-skater expected dictionaries specify every statistical column in
totals and averages mode. Traded and missing-enrichment expectations focus on the
values needed to expose those scenarios. For traded players, overall counting
averages use combined totals divided by combined games, not the mean of team
averages. Expected overall TOI is weighted by games: 19:12 overall, 02:36 PP,
00:42 SH. These fixtures assume minute/second inputs are exact; real API averages
may already be rounded.

## Field coverage audit

| Ordinary table columns | Season row keys | Source or preparation |
| --- | --- | --- |
| `games` | `gamesPlayed` | Landing season row |
| `goals`, `assists`, `points` | Same names | Landing season row |
| `plus_minus`, `penalty_min`, `shots` | `plusMinus`, `pim`, `shots` | Landing season row |
| `pp_points`, `sh_points` | `powerPlayPoints`, `shorthandedPoints` | Landing season row |
| `hits`, `blocks` | `hits`, `blocked` | Landing values when present; realtime enrichment otherwise |
| `faceoff_wins` | `faceoffsWon` | Landing values when present; faceoffwins enrichment otherwise |
| `time_on_ice` | `avgToi` | Landing season row; already a per-game time |
| `time_on_ice_pp`, `time_on_ice_sh` | `powerPlayTimeOnIce`, `shortHandedTimeOnIce` | Landing values when present; timeonice enrichment otherwise |
| Skater counting `_avg` columns | Corresponding totals keys in `sbs_stats_avg` | Core counts divided by games; hits/blocks/faceoffs need their enrichment averages |
| Goalie `wins`, `losses`, `ot_losses` | `wins`, `losses`, `otLosses` | Landing season row |
| Goalie `goals_against_av`, `saves_perc` | `goalsAgainstAvg`, `savePctg` | Supplied rate statistics; do not divide by games again |
| Goalie `saves`, `shotouts` | `saves`, `shutouts` | Saves derived from shotsAgainst minus goalsAgainst; shutouts supplied |

All currently displayed statistical categories have a corresponding SBS key or
derivation. This is a code-level contract, not proof that every saved database row
is complete. Identity, nationality and measurements remain player attributes;
`teamAbbr` identifies a historical team split, while the player's `team` foreign
key describes a different concept and must not substitute for that split.

## Known limitations reserved for subsequent commits

- The shared reader tests now verify combined traded-player totals, missing
  seasons, and missing-enrichment values against these expectations. Page
  integration is still pending; current pages do not use the reader yet.
- Current-mode updates cannot create missing season rows and copy ordinary player
  columns into the existing current-season row. Stale snapshot values can still
  reach SBS. The missing-enrichment test exercises the historical report path,
  which avoids that copying.
- Enrichment is indexed by season rather than season and team. Multiple team
  responses can overwrite each other or enrich multiple splits with the same
  values. The parser and reader tests verify preservation and combination of
  supplied splits; they do not certify the upstream enrichment.
- `get_season_by_season_average_stats` converts core counts only. Other counting
  averages require enrichment or a future complete conversion step.
- Existing full-suite collection, request-mock and database-isolation problems
  are outside this fixtures commit. Use the focused test command above.
