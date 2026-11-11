# Player profile, season history and gamelog APIs

These public read-only resources use explicit typed identity:

- `GET /api/v1/players/{player_type}/{nhl_id}/`
- `GET /api/v1/players/{player_type}/{nhl_id}/seasons/`
- `GET /api/v1/players/{player_type}/{nhl_id}/gamelog/`

`player_type` is `skater` or `goalie`; it selects the model rather than inferring
identity from current position or searching the other model. Unknown types,
missing/nonpositive/out-of-range IDs return JSON 404. Known profiles remain
available without season statistics or positive games. Requests never render
HTML, invoke loaders, make NHL calls or change records. GET/HEAD are public,
JSON-only and no-store; unsupported methods return 405 and HTML negotiation 406.
Unknown, duplicate, blank and invalid parameters return typed 400 before lookup.
The existing HTML profile, gamelog and game-detail API contracts remain intact.

## Profile

Optional `season_id` is a consecutive eight-digit ID. Omission resolves the newest
loaded NHL regular-season SBS season globally across both player types, with null
when none are loaded. A valid unloaded season stays selected. `mode=totals|averages`
defaults to totals; goalies reject averages. This mode affects selected-season
statistics and the linked season history, not the separate career packets.

The response contains:

| Field | Meaning |
| --- | --- |
| `player` | Public catalogue biography/media plus first name, birth city/state/country, draft round, current jersey number, NHL debut, roster status, captain flags and saved video URL |
| `current_team` | Current profile team identity, or null; not historical participation |
| `selected_season` | Availability/statistics packet from the shared SBS reader |
| `career_totals` | Separate packet adapted from saved `career_stats` |
| `career_averages` | Packet from saved `career_stats_avg` for skaters; null for goalies |
| `meta` | Resolved `season_id`, `player_type`, selected `mode` |
| `seasons_url` | Paginated history API path preserving the selected mode |
| `gamelog_url` | Full saved gamelog API path; apply an explicit season/date filter when needed |

Biography, jersey number, team, media and video links are current saved metadata.
Media/video destinations are not fetched or checked for availability. Positions
and notes owned by a viewer are not included. Legacy projection JSON is excluded:
its season provenance/derivation needs a separate contract before migration.

A statistics packet is `{availability, stats}`. Availability is `complete`,
`partial`, `missing` or `unverified`. No usable source means null statistics;
ambiguous/invalid SBS structures remain unverified rather than falling back to a
snapshot or a different season. Known season rows with zero games remain visible;
missing games may be null in profile/history packets. Individual unknown/invalid
values stay null. Completeness describes field availability, not source freshness
or an audit of every historical value.

`stats.kind` distinguishes `skater_totals`, `skater_averages`, `goalie_totals`, using
the [catalogue names and units](players-api.md). Counts remain integral; plus/minus
may be negative. Skater season averages are calculated by the shared reader from
SBS totals; saved `sbs_stats_avg` is not used. Per-game TOI is seconds in both modes;
goalie save percentage is a fraction and GAA is goals per 60 minutes.

Career aggregates remain independent of the loaded SBS history. They are not
summed from season rows, borrowed from current snapshot columns, or changed by the
selected season. Saved career averages retain their own values/precision and
missing fields, rather than reconstructing missing averages. Valid saved goalie
shots/goals may supply saves when the saved saves value is unavailable. Invalid
counts/rates/durations become null; zero stays zero. No refresh timestamp is
invented for player JSON without reliable source timestamps.

## Paginated season history

`/seasons/` accepts `mode`, `page`, `page_size`; it does not accept `season_id`.
One entry per normalized NHL regular-season SBS season is returned newest first:

```text
season_id
availability
stats                       # overall season, discriminated shape
contributions[]
  team                      # nhl_id, abbr, name, slug
  availability
  stats                     # exact team-season split, same selected mode
```

Overall season statistics prefer an explicit combined row, otherwise combine
unambiguous distinct splits using the shared reader. Contributions use exact team
abbreviations; `TOT`/`nTM` rows never replace a missing split. An ambiguous split
can therefore remain unverified even when the combined total is available.
Unknown teams retain their abbreviation with null ID/slug and abbreviation as name.
Current team names/slugs enrich recognized abbreviations; they are not a historical
metadata reconstruction. Invalid/non-NHL/non-regular season identifiers are not
invented as entries. Recognizable zero-game rows remain present. Non-list history
or history without recognizable seasons returns an empty list.

The standard list envelope contains `count`, `next`, `previous`, `results`, `meta`;
metadata includes typed identity and mode. Pages default to 1/50, maximum size 100.
Empty page 1 is 200; later out-of-range pages are 404. Contributions are nested
within each season rather than separately paginated. Career aggregates remain in
the profile response and are not appended as fake season rows.

## Verified saved gamelog

Omitting `season_id` returns **all saved dates**, unlike default season lists.
An optional canonical season filters known saved regular-season game IDs
(`YYYY02NNNN`), not calendar dates. Orphan dates cannot establish a season and
are excluded by that filter. Inclusive `date_min`/`date_max` use exact `YYYY-MM-DD`
schedule dates; bounds exclude unknown dates. Reversed bounds return 400.

Other parameters:

- `team`, `opponent`: exact comma-separated saved team abbreviations.
- `<stat>_min`, `<stat>_max`, `<stat>_isnull`: finite inclusive bounds or explicit
  true/false missing-value selection for the selected type's game statistics.
  Durations are seconds; save percentage is a fraction. Decision is not numeric.
- `ordering`: comma-separated `date`, `game_id`, `team_abbr`, `opponent_abbr`, or
  the selected type's game-statistic fields (including goalie `decision`), with
  `-` descending. Default `-date`. Unknown values sort last in either direction;
  final ties use date then NHL ID. Repeated/unsupported ordering fields and filters
  for the wrong player type return 400.
- `page`, `page_size`: the same 1/50 defaults and maximum 100.

All filtering/sorting precedes pagination. Metadata contains typed identity,
requested season (null means all), ordering and date bounds. Entries contain
`date`, nullable saved `game` summary, nullable `side`/`team`/`opponent`,
`game_position`, `sweater_number`, `availability`, and typed game `stats`.
[Game-detail names/units](game-detail-api.md) apply, including actual game TOI and
PP/SH seconds rather than season averages. No source arithmetic invents missing
game statistics. A game summary's freshness concerns saved game metadata; player
row availability is separate. Linked summaries also share the
[saved state evidence](game-state-api.md) object; unlinked game summaries remain
null, and storage freshness never supplies a state observation timestamp.

Known game membership comes from the typed game M2M relations. Date-specific rows
reuse the game-detail verification helper: nested player identity, explicit game
marker, compatible player type, unique roster membership, and ordered team/opponent
plus no competing same-date game for unstamped legacy rows. A stamped row cannot
supply another same-date game. Duplicate memberships or contradictory markers are
unverified, with all statistics/game position/sweater number null.

Linked games with missing rows remain visible as missing. An undated linked game
has null date and missing statistics. Valid date keys without saved roster evidence
remain orphan entries: null game/sides/teams and null statistics, explicitly
unverified for dictionary rows (missing for unusable rows). A raw game marker alone
cannot prove membership. Invalid date keys are skipped; display labels and current
profile team do not assign dates/opponents or verify statistics.

## Queries and regression coverage

An explicit-season profile uses one joined player/team read; default discovery
adds two SBS reads. History uses one player read plus one team metadata read when
recognizable seasons exist. A populated gamelog uses three reads: player JSON,
games with batched membership evidence, and prefetched sides/teams. There is no
per-game/player query growth or writer lock. Only page entries are serialized.

Projection/filtering/sorting still scale with the saved JSON history and linked
games; fixed query count is not a constant-memory or indexed-pagination claim.
Unrelated histories and snapshot columns are deferred by resource. Schema output
includes nullable, discriminated profile statistics and typed game statistics.
Synthetic PostgreSQL tests extend the existing season/trade/game fixtures and
compare game rows with the existing game-detail API. Private state, no-write/no-NHL
behavior, ambiguous/orphan/undated cases, zero/null values, pagination and query
bounds are covered alongside the legacy rendered profile regressions.
