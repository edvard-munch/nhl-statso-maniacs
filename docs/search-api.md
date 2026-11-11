# Search and autocomplete APIs

These public resources return structured saved identities, without rendered HTML,
saved-state flags or statistics. Existing HTML search/autocomplete remain available.

| Route | Result |
| --- | --- |
| `GET /api/v1/search/` | Globally paginated skater/goalie/team results |
| `GET /api/v1/search/suggestions/` | Bounded autocomplete preview without a total-count query |

Both support GET/HEAD, ignore session authentication and expose the same data to
anonymous and signed-in callers. Unsafe methods return 405. No NHL calls, domain
writes or profile/owned-data lookups occur.

## Matching and query parameters

Both resources accept:

- `q`: trimmed literal case-insensitive name substring, at most 128 characters.
  Team abbreviations also match. Omission, empty text or whitespace-only text
  returns an empty response without entity database reads.
- `entity_type`: optional distinct comma-separated `skater`, `goalie`, `team`
  codes. Omission searches all three. Explicit blank/unknown/repeated values are
  rejected; metadata reports selected types in canonical skater/goalie/team order.

Percent signs, underscores, quotes and markup-like characters are literal data,
not SQL wildcards or executable HTML. Matching uses Django/PostgreSQL's saved name
and abbreviation comparisons; there is no additional accent folding, nickname
mapping or transliteration. Players do not need current-season participation or
any valid SBS/career data to be discoverable by saved identity.

Ranking is fixed: exact name/abbreviation match, then prefix, then other substring
matches. Ties use database `LOWER(name)`, typed group order (skater, goalie, team)
and NHL ID. This differs intentionally from the legacy endpoint's insertion/group
ordering. No arbitrary ORM filters or client-supplied ordering expressions exist.
Unknown/duplicate query parameters, invalid types/limits and overlong/null-character
queries return 400 before database access.

## Identity DTO and navigation

Every result has the same explicit fields:

```json
{
  "entity_type": "skater",
  "nhl_id": 8478402,
  "name": "Example Player",
  "slug": "example-player",
  "image_url": "/media/players_pics/example.png",
  "position_abbr": "C",
  "abbr": null
}
```

For teams, `position_abbr` is null and `abbr` contains the saved team abbreviation.
For players, `abbr` is null; no current-team relation or private position override
is inferred. An empty image field produces a null URL. Image URLs use the relevant
model's configured storage; search never opens image bytes or tests file existence.
Names/slugs/positions describe current saved metadata, not historical reconstruction.

The frontend builds navigation from typed identity: skater/goalie results map to
`/api/v1/players/{entity_type}/{nhl_id}/` and team results to
`/api/v1/teams/{nhl_id}/`. Slugs remain available for the frontend's route choices.
Equal NHL IDs or database primary keys across models do not collapse results.
Database primary keys are not exposed. Render plain names with normal escaped Vue
interpolation, not `v-html`; there are no anchor labels, grouping separators or
special “full results” sentinel records.

## Paginated full search

`/api/v1/search/` accepts ordinary `page` and `page_size` (default 50, maximum 100).
The response has `count`, `next`, `previous`, `results`, and metadata:

```json
{
  "q": "example",
  "entity_types": ["skater", "goalie", "team"],
  "ordering": "relevance,name,entity_type,nhl_id"
}
```

Count, ranking, LIMIT and OFFSET apply to the combined selected entity set. Results
are not independently sliced per model or loaded entirely into Python. Links
preserve encoded query text and filters. Empty first pages return 200; later
out-of-range pages return 404. A nonempty matching page uses two database queries
(count and selected page); an unmatched query needs only the count. Membership and
season selections do not affect these counts. Metadata refreshes can move results
between pages; this is offset pagination, not a revision/cursor snapshot.

## Bounded suggestions

`/api/v1/search/suggestions/` accepts `limit` (default 10, maximum 20), not page
parameters. It returns `results` and metadata only:

```json
{
  "q": "example",
  "entity_types": ["skater", "goalie", "team"],
  "ordering": "relevance,name,entity_type,nhl_id",
  "limit": 10,
  "has_more": true
}
```

The endpoint uses one query for at most `limit + 1` selected identity rows, with no
COUNT. `has_more` indicates matches beyond the preview; it is not a total count or
per-type quota. Results use exactly the full-search DTO and ranking. The frontend
can offer a full-search action using the same query/types and build that page's URL
itself. Blank queries return an empty preview with `has_more: false` and no reads.

## Privacy, schema and rollout

Both resources explicitly allow public access and disable session authentication,
so they do not read users, favorites, comparison, notes, private positions or
preferences while assembling results. Current API cache policy uses no-store;
there are no viewer-dependent result fields to mix into a shared public cache.
Statistics and raw SBS/career/gamelog JSON are not selected from the database.
OpenAPI describes typed identity and both response shapes.

No migrations, dependencies, frontend routes or legacy contract changes are
introduced. Before frontend scaffolding, review the API workflow inventory and
remaining provenance decisions; completing this family does not by itself prove
that every UI workflow has a replacement. Then introduce Vue/Vite and generated
client checks in focused commits, retaining existing pages until tested cutover.
