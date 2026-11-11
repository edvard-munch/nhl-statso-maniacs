# Private player notes and position overrides

These session-private resources apply to the current account and an explicitly
typed player. Favorites/comparison membership is not required. Existing HTML/AJAX
editors remain available and use the same private-record lookup and writer.

## Routes

| Route | Methods |
| --- | --- |
| `/api/v1/me/players/{player_type}/{nhl_id}/note/` | GET, PUT, DELETE |
| `/api/v1/me/players/{player_type}/{nhl_id}/positions/` | GET, PUT, DELETE |

`player_type` is `skater` or `goalie`; NHL IDs are positive signed-32-bit integers.
A known typed player is required for every operation, including DELETE; invalid
or missing targets return 404. No database primary keys, author IDs, content type
IDs or player names may select a private record through this API.

A Django session is required; anonymous requests return 403
`authentication_required`. Responses are private/no-store and vary on Cookie.
PUT/DELETE require [session CSRF](session-auth-api.md). Query parameters are rejected.
PUT accepts a JSON object with exactly the required field below. DELETE accepts
an empty body or empty JSON object. POST/PATCH are not supported. GET/HEAD never
create, upgrade, repair or delete records.

## Note contract

PUT performs an explicit full replacement:

```json
{"text": "Watch on the power play"}
```

The existing `NoteForm` policy applies: trim surrounding whitespace, maximum 400
characters after trimming, and reject null characters. JSON text must be a string;
null, booleans, numeric values and collections are rejected. Empty/whitespace-only
text clears the note. Text is plain text, including any markup-like characters;
the future frontend must render it through normal escaped Vue interpolation.

GET and successful PUT return:

```json
{
  "player_type": "skater",
  "nhl_id": 8478402,
  "source": "typed",
  "text": "Watch on the power play"
}
```

A known player's virtual resource exists even without a stored note. Its response
has `text: null` and `source: none`; GET and PUT return 200. DELETE returns 204 with
no body, including when already absent. Repeated replacement preserves one record
and its ID rather than appending duplicate notes.

## Position contract

PUT performs an explicit full replacement:

```json
{"positions": ["C", "LW"]}
```

The existing `PositionsForm` choices are **D, C, LW, RW** for both player models.
This preserves legacy behavior rather than inventing a new goalie policy. Codes
are case-sensitive; G/L/R and unknown values are rejected. Input must be an array;
duplicates are removed while retaining input order. An empty array clears the
override. It does not change the official saved player position or public stats.

GET and successful PUT return:

```json
{
  "player_type": "skater",
  "nhl_id": 8478402,
  "source": "typed",
  "positions": ["C", "LW"],
  "official_position": "C",
  "effective_positions": ["C", "LW"]
}
```

Without a safe override, `positions` is null and `effective_positions` contains
the official saved position, or an empty array when that metadata is blank. An
official goalie position therefore falls back to `["G"]`, even though G is not a
private override choice. Official metadata is current, not historical. Existing
invalid/empty stored arrays return `source: invalid` and the official fallback;
reads do not repair them. A valid replacement can correct the selected record.
GET/PUT return 200; DELETE returns 204, including when already clear.

## Source and legacy attribution

Both responses explicitly describe private-record provenance:

| Source | Meaning |
| --- | --- |
| `none` | No safely attributable private record |
| `typed` | One record for this account, player model and database object ID |
| `legacy` | One untyped row, with no player in the opposite model sharing its object ID |
| `ambiguous` | Duplicate typed rows, duplicate untyped rows or an untyped row whose object ID could identify both player models |
| `invalid` | Selected position data does not form a nonempty valid override |

Typed lookup takes precedence. A single safely attributable untyped row can be
read without writes and is upgraded in place on a valid edit. Names do not resolve
cross-model ambiguity. Unrelated accounts and the other player type are excluded,
even when player database IDs or NHL IDs coincide.

Ambiguous untyped rows are preserved and never exposed. A valid nonempty explicit
replacement can create a separate typed record. Clearing does not delete those
ambiguous rows. Multiple typed records return null private values on GET;
PUT/DELETE return 409 `private_player_data_conflict`, preserving all rows for review.
Legacy editors also reject those conflicting writes instead of choosing a row.

Clearing a typed record also removes a shadowed **single safely attributable**
untyped row so the old value cannot reappear on the next read. Ambiguous legacy
rows remain untouched. This is a targeted explicit clear, not a legacy-data backfill
or inferred association. The broader ambiguous-data review remains separate.

## Transactions and validation

API reads/writes and legacy editor writes use the existing transactional account
row lock, shared with saved-list changes. Lookup, mutation and API serialization
remain inside the lock. Competing API/legacy creates cannot insert two records;
repeated replacement/clear converges to the explicit requested state. Unrelated
accounts do not share a lock. Failed validation, typed conflicts and serialization
failures leave existing data intact.

There is no new database uniqueness migration. Direct SQL and future writers must
also follow this owner-lock contract. Requests serialize by lock acquisition;
responses are not a revision protocol and frontend responses can arrive out of
order. Notes and positions never appear in public cached statistics responses.

No migrations, dependencies, loader calls or frontend changes are introduced.
[Account settings](account-api.md) and [profile images](account-image-api.md) are
implemented, as is [search/autocomplete](search-api.md). Review remaining workflow
contracts before Vue/Vite scaffolding.
