# Loader HTTP retries and cooldowns

`make update-daily` / `make update-all` keep their sequential, stop-on-failure
behavior. Loaders share `players/nhl_http.py` for team/player reports, season
detection, current/full totals, player landing responses, game JSON/HTML reports,
and team/profile image downloads. Legacy projection/season command entry points
have been retired; their command-specific transport check is removed.
The six obsolete `_new/` experiments have been retired; supported loader behavior
is unchanged. See the [legacy inventory](legacy-audit.md).

## Limits and recovery

| Setting | Behavior |
| --- | --- |
| Attempts | At most three attempts per request, including the initial request. |
| Timeout | Ten seconds by default; existing explicit timeouts remain (season detection/legacy player helper: three seconds). |
| Transient failures | Connection/timeouts, interrupted/invalidly encoded bodies, HTTP 408, 429 and server errors can retry. Required game/report JSON validation shares the same attempt budget. |
| Backoff | One then two seconds; HTTP 429 uses five then ten seconds when no longer server cooldown applies. |
| `Retry-After` | Accept nonnegative integer seconds or an HTTP date; wait at least the suggested delay and the fallback backoff. Invalid/past values use backoff. |
| Maximum wait | Sixty seconds per retry. A longer server cooldown ends that request with an error instead of retrying earlier than requested. |
| Permanent HTTP errors | Other client errors, including 400/401/403/404, are not retried. Existing optional missing-data behavior remains. |

The constants are in `players/nhl_http.py`. Request timeouts apply per attempt
and are not an overall command deadline. Retries log the endpoint, attempt and
wait in seconds, then release the failed response before waiting. Pagination
retries the same page with the same parameters; no request-adapter retry layer
is added. The policy follows the HTTP [Retry-After specification](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after).

Required failures identify the endpoint/context and number of attempts and stop
the command. Optional career/HTML/image requests can still fall back after
non-rate-limit failures, preserving existing missing-data behavior. Exhausted
HTTP 429 stops even optional requests; it cannot silently become empty career
data or a fallback season, or continue through all remaining players.

Retries do not roll back earlier successful loaders or players. Existing player
publication and per-game/day transaction boundaries are unchanged. The read-only
TOI audit retains its own pacing, rate-limit stop and checkpoint behavior.

## After an exhausted rate limit

Allow the service to recover before rerunning. When players already completed
and current totals failed, rerun just the remaining stages:

```bash
uv run --locked python manage.py upd_pls_tot --mode=current &&
uv run --locked python manage.py upd_gms
```

Current totals starts at the beginning; it does not resume at the failed progress
index. There is no guarantee that retrying will avoid a rate limit: the service's
quota/window is not known. A server cooldown over the automatic limit requires
waiting and a later manual rerun.

## Verification

`tests_nhl_http.py` mocks responses, clocks and sleep calls. It covers numeric/date
cooldowns, missing/malformed/past headers, long-wait refusal, exponential backoff,
bounded exhaustion, permanent HTTP errors, transport recovery, response cleanup,
session/parameter preservation and a combined HTTP/JSON retry budget. Loader-entry
checks cover teams, season detection, season reports, landing/career endpoints,
games, HTML and images. Existing persistence tests protect rollback
and optional-career preservation; persistent 429 leaves the current player unchanged.
Offline tests replace waits; explicitly marked live API tests retain real waits.
