# Saved game-state evidence

Every saved game summary now includes `state`, shared by the scoreboard, game
detail, public player gamelogs and aggregated Favorites gamelogs. Existing scores,
`is_final` and freshness fields retain their contracts. No models, loaders or
upstream requests change; no backfill or database write is involved.

```json
{
  "value": "live",
  "source": "legacy_result",
  "observed_at": null,
  "conflict": false
}
```

`value` is `live`, `final` or `unknown`. It is a **saved assertion**, not a promise
about the game's current NHL status. `source` is `legacy_result`,
`legacy_final_flag` or null. `conflict` reports contradictory verified assertions.

## Conservative evidence rules

Result-based evidence uses the same strict parser as numeric scores: exactly one
away and one home side, distinct teams, the exact ordered saved team-name prefix,
nonnegative integer scores and a recognized whole-string suffix. Malformed,
renamed, reordered or ambiguous side/team/result data cannot establish result state.

| Saved evidence | State | Source | Conflict |
| --- | --- | --- | --- |
| Verified `(Live)` result; final flag false | `live` | `legacy_result` | false |
| Verified `(Live)` result; final flag true | `unknown` | null | true |
| Final flag true, without verified live conflict | `final` | `legacy_final_flag` | false |
| Verified `OT` or `SO` final result; final flag false | `final` | `legacy_result` | false |
| Everything else | `unknown` | null | false |

The loader emits an OT/SO outcome suffix only for a finished game. Its final flag
also depends on roster publication; false therefore does not establish that a
game is still being played. A verified OT/SO result may report `state.value=final`
while the preserved `is_final` flag remains false. The final flag is independent
saved game-ID evidence and can report final even if scores or side data are
unavailable; result freshness/partial metadata still identifies those omissions.

A plain score, including `0:0`, cannot distinguish final, live, intermission or an
incomplete legacy record. A blank result cannot distinguish scheduled and pregame
states. These remain unknown unless a positive final assertion exists. A trailing
word resembling Live outside the verified format is not live/conflict evidence.

## Observation time and storage freshness

`observed_at` is **always null for these legacy sources**. `Game.updated_date` can
change independently of the result or final flag, and some field-specific saves
do not update it. Neither it nor the API request's check time establishes when NHL
observed the state. The API does not manufacture a state observation timestamp or
state observation age.

Existing `freshness.saved_at`, `age_seconds`, `is_stale` and `checked_at` describe
saved record storage and the API check. They are not an observation clock for
`state`. An old saved live assertion remains live evidence with unknown observation
time, and does not become final or unknown merely through age. Conversely, a fresh
save does not make an unknown state live or prove that legacy state evidence is
current. Final storage freshness behavior remains unchanged, including when the
state object reports a live/final conflict. Clients must inspect `state.conflict`
and avoid presenting conflicting or undated assertions as confirmed current status.

This slice deliberately does not read `ScheduledGame`: scheduler `discovered_at`
marks schedule discovery, independently of boxscore/result evidence. A future
qualified schedule-state contract must expose its own source, identity/date checks,
observation time and precedence rather than silently replacing this evidence.

No raw `Game.result` or private fields are returned for frontend parsing. Shared
state projection adds no database queries; missing linked game summaries in
legacy gamelog rows remain null rather than gaining guessed states. Start time,
period and clock remain separate possible enhancements.
