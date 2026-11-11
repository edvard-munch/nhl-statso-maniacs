# Saved game-detail JSON API

`GET /api/v1/games/{nhl_id}/` is a public read of one saved game. It does not run
loaders, contact NHL/report/image services, render templates or change application
records. It accepts no query parameters; unknown parameters return typed JSON 400.
Unknown/nonpositive/out-of-database-range IDs return JSON 404. Unsupported writes
return 405. HEAD has the same status/headers as GET with no body. Responses are
no-store and independent of the current viewer's saved lists or private data.
The legacy game page and AJAX refresh endpoints remain operational.

## Summary and rosters

The response extends the [scoreboard game object](scoreboard-api.md) with `rosters`:

```text
rosters
  away
    forwards[]
    defencemen[]
    goalies[]
  home
    forwards[]
    defencemen[]
    goalies[]
```

Teams, verified legacy scores, outcome/source and final status use the same shared
adapter as the scoreboard. No new score/state persistence is implied. A saved game
without a gameday returns null `date`, missing player statistics and partial
freshness rather than borrowing another date or reporting an unknown game.

Roster membership comes from the six game M2M relations, not players' current
team foreign keys or all entries found in their gamelogs. Lists are ordered by
current saved `last_name`, then NHL ID. Empty groups are explicit empty lists;
bench players not linked to the game are not added. A roster with no skaters or no
goalies on either side contributes to partial freshness. An empty defencemen or
forwards subgroup alone does not prove an incomplete roster.

Each player exposes `player_type`, `nhl_id`, `name`, `last_name`, `slug`, current
`position_abbr`, date-specific `game_position`, `sweater_number`, `availability`
and an explicit `stats` object. Skater and goalie identities remain typed even
if their database primary keys coincide. Current profile fields are not historical
reconstructions. No internal primary keys, complete gamelog/career/SBS blobs,
notes, favorite flags, account fields or HTML labels are included.

## Which saved row is trusted

Only the gamelog key matching this game's saved schedule date is fetched. A row
must have matching nested `player.nhl_id` identity. If `gameId` exists, it must
match this game; a wrong/null/malformed marker never falls back to team matching.
An explicitly contradictory goalie/skater position also makes the row unverified.
Repeated membership of the same typed player across this game's roster groups
is ambiguous and cannot produce verified statistics in either position.

An unstamped legacy row additionally requires matching **ordered** team/opponent
abbreviations, distinct unambiguous game sides and no other same-date game linked
to that typed player. Conflicts are checked in batches through the appropriate
skater/goalie M2M relations. Do not guess an assignment, modify legacy rows or
use current season/profile snapshot statistics as substitutes.

| Availability | Meaning |
| --- | --- |
| `complete` | Identity is verified and all requested player fields are known/valid. |
| `partial` | Identity is verified but some requested fields are missing or invalid. |
| `missing` | No usable dictionary exists for this date, including an undated game. |
| `unverified` | A date row exists but identity/game/legacy evidence is contradictory or ambiguous. |

Missing/unverified rows retain the known roster identity while all statistics,
sweater number and game position are null. Partial rows retain valid fields.
Completeness is a field-availability check, not a consistency audit of every saved
number or proof that the NHL has finalized all reports. A decision can naturally
be unavailable during a live game or for a goalie without an assigned outcome.

## Statistics and units

Skater fields are `goals`, `assists`, `points`, `plus_minus`, `penalty_minutes`,
`shots_on_goal`, `hits`, `blocked_shots`, `faceoffs_won`, `pp_points`, `sh_points`,
`toi_seconds`, `pp_toi_seconds`, and `sh_toi_seconds`. Counts are saved game counts,
not per-game season averages; no totals are reconstructed from other fields.
Negative plus/minus is valid. Other count fields are nonnegative integers.

Goalie fields are `decision`, `toi_seconds`, `goals_against`, `saves`,
`shots_against`, `save_percentage`, and `shutouts`. Decision accepts saved W/L/O/OT;
other values remain null. Save percentage is a finite fraction from 0 to 1,
not a 0–100 percentage. Per-game shutouts is a saved 0/1 value, not inferred from
other fields by this read. Explicit saved `saves`/`shotsAgainst` fields take
precedence; absent ones may use a strictly parsed `saveShotsAgainst` pair. A pair
with more saves than shots is not verified.

TOI values are numeric seconds, parsed only from valid saved minute:second strings.
Thus `12:34` is 754, `00:00` is 0, and missing/malformed values such as `00:60` are
null. Unknown values never become zero. Numeric count strings may be normalized;
booleans, fractional counts, invalid signs and values outside signed 32-bit count
bounds are rejected rather than truncated. Nonfinite/out-of-range goalie fractions
are null. The frontend owns all time/percentage/name formatting.

## Freshness, queries and verification

Save/check times, final/nonfinal aging and stale thresholds are shared with the
scoreboard. Here `freshness.partial` additionally includes missing/unverified
player fields and missing roster data. It can differ from scoreboard partial,
which assesses only scoreboard team/score fields. A successful read never advances
save time or implies new NHL data.

The lookup selects the game/gameday, sides/teams and six roster groups in eight
SELECTs. PostgreSQL extracts only the requested date's JSON value; full history
and unrelated profile/statistics fields are deferred. Unstamped rows add at most
one batched collision query per player model, for a maximum of ten SELECTs rather
than a per-player query. No advisory locks or row locks are acquired.

The public OpenAPI schema declares the typed nested rosters, nullable statistics
and units, and normal offline tests validate schema export without network calls.
Synthetic tests cover loader-produced data, conflicting snapshots/history,
identity collisions, missing/null/malformed values, read-only bounded queries,
legacy ambiguity and preservation of the existing scoreboard/page contracts.


## Shared saved-state evidence

Game detail includes the same [state object](game-state-api.md) as the scoreboard
and linked gamelog summaries. Live/final assertions require qualified saved
evidence; unknown/conflicting states are explicit. Observation time remains null
for legacy evidence and is independent of storage freshness and roster completeness.
