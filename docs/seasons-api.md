# Loaded seasons JSON API

`GET /api/v1/seasons/` is public and read-only. It discovers loaded NHL
regular-season seasons from skater and goalie `sbs_stats`, using the same shared
reader as the existing Players page. It never invokes loaders or NHL requests.

Canonical IDs and legacy display labels are normalized to eight-digit strings,
deduplicated and sorted newest first. Invalid seasons/rows and non-list JSON are
ignored. Explicit non-NHL leagues and non-regular game types are excluded; absent
league/game-type markers retain the existing NHL/regular-season defaults. A row
establishes availability even with zero games or incomplete statistics; discovery
does not certify that every player's season statistics are complete.

Snapshot fields, `stats_season_id`, `sbs_stats_avg`, games and the current calendar
do not establish a loaded SBS season. No missing season is synthesized.

Example response:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {"season_id": "20262027", "label": "2026-27"},
    {"season_id": "20252026", "label": "2025-26"}
  ],
  "meta": {"default_season_id": "20262027"}
}
```

Only `page` and `page_size` are accepted: positive integers, defaults 1/50,
maximum page size 100. Unknown/duplicate/blank/invalid query parameters return
JSON 400 before database access. The default season is the newest season across
the entire collection, independent of the requested page. Empty page 1 returns
200 with count 0, empty results, null navigation and null default season. Other
out-of-range pages return JSON 404. Unsupported methods return JSON 405.

Responses are JSON-only and no-store, identical for anonymous and authenticated
viewers. HEAD is supported. Discovery reads only the two models' SBS columns
(two queries, independent of player count); it scans stored rows rather than a
separate indexed seasons table. No private fields, writes or writer locks are
involved. OpenAPI describes the response, pagination and error contracts.
