# Players catalogue JSON API

`GET /api/v1/players/` is a public, read-only catalogue of players with positive
known games in a selected loaded NHL regular season. It uses
`players.season_stats.read_season_stats`, also used by the existing tables.
No NHL requests, loaders, writes or private membership lookups occur.

## Selection and pagination

- `season_id`: consecutive eight-digit string, e.g. `20262027`. Display labels
  are not accepted by this API. Omission selects the latest valid loaded SBS
  season across both player types, independent of the calendar or filters.
- `player_type=skater|goalie`, default `skater`; this endpoint returns one type.
  NHL identity is always the pair of `player_type` and `nhl_id`.
- `mode=totals|averages`, default `totals`. Goalies accept only `totals`, which
  includes their rates; requesting goalie averages returns 400.
- `page` and `page_size`: positive integers, defaults 1/50, maximum size 100.

The envelope is `count`, `next`, `previous`, `results`, `meta`. Metadata contains
resolved `season_id` (null if nothing is loaded), `player_type`, `mode` and the
ordering applied. Empty page 1 returns 200, count 0 and empty results. Other
out-of-range pages return JSON 404. A valid explicitly requested empty season
remains selected; no older statistics are substituted.

Snapshot columns, `stats_season_id`, career/gamelog JSON and `sbs_stats_avg` never
supply season statistics or membership. Missing season rows, unknown/nonpositive
or fractional games and ambiguous/malformed SBS structures are excluded. Invalid
SBS structures are logged without raw JSON. An individual unknown statistic is
null, not zero; a partial player remains in the catalogue when games are known.

## Response entries

Each entry explicitly includes public identity (`player_type`, `nhl_id`, `name`,
`last_name`, `slug`), `image_url`/`nation_flag_url`, current profile position and
nationality names/abbreviations, `birth_date`, `age`, `height_cm`, `weight_kg`,
`weight_lb`, `draft_year`, `draft_number`, `rookie`, season `teams`, `availability`
and `stats`. Image fields are storage URLs (or null); URLs are not checked for
file existence. No rendered HTML, favorite/comparison flags, notes, personal
positions, database PKs or raw JSON histories are exposed.

Biography is current profile data, not historical reconstruction. Both stored
weight units are exposed to preserve existing display values without conversion
rounding. Age is the saved profile value; the endpoint does not recompute it.

`teams` contains distinct season participation, sorted by abbreviation, with
`nhl_id`, `abbr`, `name`, `slug`. Unknown team abbreviations remain available with
null ID/slug and abbreviation as name. Combined `TOT`/`nTM` rows are not invented
as team identities. Profile current-team foreign keys do not establish historical
participation. Current team names/slugs enrich known season abbreviations.

`availability=complete|partial` describes the returned statistical fields only;
it does not certify upstream completeness, identity metadata or current freshness.
Player records lack a reliable season refresh timestamp, so no freshness time is
invented here. The API reads saved state even if loaders have not run recently.

`stats.kind` is an OpenAPI discriminator:

| Kind | Fields and units |
| --- | --- |
| `skater_totals` | Integer `games`, `goals`, `assists`, `points`, `plus_minus`, `penalty_minutes`, `shots_on_goal`, `hits`, `blocked_shots`, `faceoffs_won`, `pp_points`, `sh_points`; nullable per-game `avg_toi_seconds`, `avg_pp_toi_seconds`, `avg_sh_toi_seconds` |
| `skater_averages` | Same names; `games` stays an integer, counting statistics become per-game numbers using shared-reader rounding; ice time remains per-game seconds |
| `goalie_totals` | Integer `games`, `wins`, `losses`, `ot_losses`, `saves`, `shutouts`; nullable `goals_against_average` (per 60 minutes) and `save_percentage` (fraction 0–1) |

Only `games` and `kind` are non-null statistical fields. Finite integral counts
remain integers; malformed/fractional/negative counts become null (signed
plus/minus remains valid). Known zeros remain zero. Missing skater averages stay
null when their source total is invalid. Supplementary durations are validated
and exposed as seconds. Traded-season totals prefer explicit combined rows,
otherwise combine distinct contributions using the shared reader. Combined goalie
GAA remains null when reliable ice time is unavailable; save percentage uses the
reader's weighted saved shot/save counts rather than an average of percentages.

## Filters and ordering

Filtering and sorting operate on projected values **before pagination**. The API
uses named parameters; legacy positional column/widget URLs are not accepted.

- `search`: trimmed, case-insensitive literal name substring; no regex/wildcards.
- `team`, `position`, `nation`: distinct comma-separated exact, case-sensitive
  abbreviations. OR within a field; AND between fields. Position/nationality use
  current profile attributes. `team` selects season participants but preserves
  their overall season totals; team-only contributions belong to the later team API.
- `rookie`: exact `true` or `false`; omission leaves both groups eligible.
- `birth_date_min`, `birth_date_max`: inclusive `YYYY-MM-DD` bounds.
- `<field>_min`, `<field>_max`: inclusive finite numeric bounds, in the selected
  mode and units above. Supported fields are the selected type's statistics plus
  `age`, `height_cm`, `weight_kg`, `weight_lb`, `draft_year`, `draft_number`.
  Missing values do not match numeric bounds.
- `<field>_isnull=true|false`: select missing/known values for the same numeric
  fields. Other filters still apply; this does not turn null into zero.
- `ordering`: comma-separated fields; prefix `-` for descending. Allowlisted
  fields are the selected type's numeric fields plus `name`, `last_name`, `nhl_id`,
  `position_abbr`, `nation_abbr`, `birth_date`. Unknown values sort last in both
  directions. Default skater ordering is `-points,last_name,nhl_id` (points per
  game in averages); goalie ordering is `-wins,last_name,nhl_id`. Final ties use
  case-insensitive last name then NHL ID, independent of database insertion order.

Unknown, duplicate, blank or invalid parameters, inappropriate player-type fields,
repeated ordering fields and reversed bounds return typed JSON 400 before database
access. A valid filter with no matches returns an empty list. Query examples:

```text
/api/v1/players/?season_id=20262027&mode=averages&goals_min=0.5&ordering=-points
/api/v1/players/?player_type=goalie&save_percentage_min=0.9
/api/v1/players/?team=BUF,COL&position=C,D&page_size=25
```

## Query strategy and verification

Selected-season projection/filtering/sorting runs in Python against SBS arrays,
matching the current storage model. Explicit-season requests use two read queries
(teams and selected player type); omitted seasons add the two-model discovery
queries. Query count does not grow with the returned population. Only page entries
are serialized and their media URLs resolved. Unrelated histories, snapshot fields,
private data and current-team relations are deferred. CPU/memory still scale with
the candidate set and stored SBS history; indexed relational seasons are a separate
future optimization.

Anonymous and signed-in callers receive the same JSON/no-store response. HEAD is
supported; unsupported methods return 405, HTML negotiation 406. OpenAPI describes
filters, errors and discriminated statistics variants. Tests use synthetic
PostgreSQL fixtures and mocked NHL requests, extending the existing season fixtures.
The existing HTML/AJAX Players tables remain unchanged.

## Complete filter metadata

`GET /api/v1/players/filters/` returns the full selected-season filter population,
independent of catalogue pages. It accepts the same validated filters, type and
mode as `/players/`, but rejects `page`, `page_size` and `ordering`. Default season
resolution, positive known GP membership, current biography, partial statistics,
team participation and missing registry fallbacks are shared with the catalogue.
No private state, upstream calls or database writes are involved.

The response contains:

- `meta`: resolved `season_id` (nullable), `player_type`, `mode`.
- `initial_count` and `initial_ranges`: before any filters, after season/type/mode
  selection. These establish the slider domains.
- `options_count` and `options`: after all filters **except** `team`, `nation` and
  `position`. All three categorical selections are ignored together so selecting
  one checkbox does not hide alternatives. Search, rookie, birth date and numeric
  filters still affect options. Teams use the catalogue identity DTO; nations and
  positions are `{code, label}`. Values are sorted by code, empty codes omitted,
  empty labels fall back to the code. Conflicting biography labels use the lowest
  NHL identity's label, deterministically.
- `filtered_count` and `filtered_ranges`: after every filter, matching the
  catalogue's unpaginated count. Each range is `{min, max}`. Numeric keys cover all
  allowlisted fields for the selected player type, including biography, GP and
  mode-specific statistics; unknown values are excluded and known zero retained.
  No known values produces two null bounds. TOI is seconds, save percentage a
  fraction, height centimetres and weight explicitly kg/lb. Counts are numeric
  range bounds, not formatted labels.
- `height_values_cm`: sorted distinct known heights after every filter, for a
  discrete height control. Empty populations return `[]`.

For example `/api/v1/players/filters/?season_id=20262027&nation=CAN` retains
all nations in the options population, while the filtered ranges describe only
Canadian players. Changing `mode=averages` changes the statistic ranges as well.
The resource is not paginated; its bounded option sets and range keys describe the
complete population. An explicit season uses two read queries regardless of row
count; default season discovery adds its usual queries. Player rows are projected
in memory just as for the catalogue, so work grows with the saved player population.

These are **public Players** facets. Favorites retain missing/zero-season members;
private filters must use a private scoped contract or an explicitly complete
private collection, rather than silently using these public membership rules.
