# Private player notes and extra positions

Notes and extra positions belong to the authenticated user **and** a particular
player model/ID. A skater and goalie may share a database primary key, so their
content type is part of every new record's identity. The player URL selects the
target; submitted author/object identifiers do not select another user's data.

## Editing and validation

- Notes accept up to the model's 400-character limit. Text is trimmed; empty text
  clears the current user's note for that player. Rendered profile text is escaped.
- Extra positions use the existing checkbox values D, C, LW and RW. Only validated
  `check` values are stored, with duplicates removed. No selections clears the
  override and the response displays the player's default position again.
- Invalid form submissions return HTTP 400 with JSON `errors`, preserving the
  existing record. Missing player identities return 404 for authenticated edits.
- Anonymous requests retain the existing JSON `authenticated: false` contract
  and perform no writes. GET requests retain their existing response contract and
  do not create/update/delete records. POST requests require Django's CSRF token.

Normal repeated edits update one existing record rather than creating another;
clearing an already-empty override is harmless. Profiles show only the requesting
user's data for the selected player type. Database uniqueness constraints and
concurrent-edit policies are separate work; this batch does not introduce a schema
migration or a bulk cleanup command.

## Compatibility with old records

Earlier endpoints saved rows with a null `content_type`. The application now
prefers correctly typed records. If no typed record exists, it reads a single
legacy row only when its numeric player ID exists in just one player model.
Editing that row fills in its content type without changing its primary key;
explicitly clearing it deletes only that user's unambiguous row.

If the ID exists in both player models, or multiple untyped rows exist for the
same user/ID, the legacy data is **preserved but not shown or guessed**. A new edit
creates a correctly typed record alongside it. Ambiguous legacy rows need a
separate review before any manual assignment or deletion; no bulk reassignment
or application-database changes were performed by this implementation.

## Regression checks

Using the [isolated test database setup](testing.md):

```bash
python -m pytest -c players/tests/pytest.ini players/tests/integration/tests_owned_player_data_db.py
```

Twenty cases cover colliding skater/goalie primary keys, different users, forged
identifiers, repeat updates/clears, note length, invalid positions, missing players,
anonymous posts, CSRF, escaped/private profile rendering and legacy preservation/
upgrade. HTTP is blocked and real PostgreSQL records are rolled back after tests.
