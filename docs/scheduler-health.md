# Read-only scheduler health

Use this before or after enabling automation:

```bash
uv run --locked python manage.py scheduler_health
uv run --locked python manage.py scheduler_health --json
```

The command reads saved PostgreSQL evidence only. It never creates scheduler
state, acquires loader/job locks, repairs records, runs loaders, calls NHL APIs,
contacts RabbitMQ or inspects service processes. Scheduling must be activated
separately. An enabled installation with no success markers is unhealthy due to
missing evidence; the command does not initialize it or invent a deadline.
Disabled scheduling skips database checks entirely.

## Output and monitoring

| Exit code | Status | Meaning |
| --- | --- | --- |
| 0 | `healthy` | No configured saved-state health checks failed. |
| 1 | `unhealthy` | Missing/overdue successful updates, unresolved recent failures/interruption, or a long-running loader. |
| 2 | `disabled` | Scheduling is disabled; no database health checks were performed. |
| 3 | `unknown` | Database/table access failed or command thresholds are invalid. |

`--json` emits one object to stdout, including on unhealthy/disabled/database-error
outcomes; Django's short nonzero-status message goes to stderr. Invalid arguments
or settings/startup errors use the normal Django/argparse error path and may not
produce JSON. Do not merge stderr into the JSON stream. Callers should read
`status` first: disabled/unknown results do not contain the full job details.
The schema currently has `schema_version: 1`; timestamps are UTC and daily/weekly
markers are the UTC maintenance-window start dates.

The full report includes safe schedule settings, check thresholds, per-job
last success/due/overdue information, eligible/due/overdue game counts and samples,
active cooldown, recent failed/interrupted runs and current running work. Game
and run details are bounded by `--limit`; issue counts use all matching rows, so
a small display limit cannot make an unhealthy report healthy. No broker URL or
environment credentials are included. Human output shows the same core evidence.

Defaults can be adjusted for a deliberately long refresh or server cadence:

```bash
uv run --locked python manage.py scheduler_health --json \
  --grace-seconds 900 --max-run-seconds 3600 \
  --failure-lookback-hours 24 --limit 20
```

Grace can be 0–604800 seconds, the run threshold 1–604800 seconds, lookback 1–720
hours and display limit 1–1000. The defaults are 15 minutes of grace, a one-hour
run threshold, 24 hours of failure history and 20 detailed rows per section.

## How checks are interpreted

- **Discovery:** its successful timestamp is due at the configured near-game or
  quiet cadence and overdue only after the additional grace period.
- **Daily:** the success marker must cover the most recent quiet window whose
  end plus grace has passed. A job can be due within a window without being
  unhealthy. Midnight-crossing windows belong to their start date.
- **Weekly:** the current week's success is required after the configured weekday's
  quiet window plus grace. Bootstrap success earlier in the same week counts,
  matching scheduler behavior. Windows crossing Sunday/Monday are handled in UTC.
- **Maintenance eligibility:** active/imminent games or an outside-window check
  are shown as blockers. A blocker does not erase an already missed deadline.
- **Live/final games:** health and execution share the read-only candidate selector,
  including snapshot recency, schedule state, active-age and final retry-window
  rules. Last attempts determine due work; successful `Game.updated_date` publication
  determines overdue work, with the cadence plus grace allowed from game start or
  first final discovery. An earlier live save does not make a newly discovered
  final immediately overdue. Rows outside the final retry window are excluded;
  delayed reports/corrections then belong to daily reconciliation or explicit audits.
- **Failures/interruption:** recent means the terminal completion time (falling
  back to start time if absent). A later successful run with the exact same
  command and JSON scope marks that failure recovered in this report. Different
  games, modes or selectors cannot clear it. Counts include every unresolved
  matching failure, not just the displayed sample. Recorded failures are never
  rewritten; inspect their UUIDs with `loader_status` and application logs.
- **Long-running work:** elapsed time since start exceeds `--max-run-seconds`.
  Progress timestamps are displayed, but an old timestamp does not prove a crash;
  there is no background request heartbeat. The command never marks a run interrupted.
- **Cooldown:** reported as an expected temporary deferral, without making the
  report unhealthy by itself. It does not excuse indefinitely overdue work.

A healthy result is not proof of current Beat/worker/broker availability, source
freshness, complete optional statistics, successful task-result cleanup or a valid
backup. Manual runs can refresh game data, and deleted/expired run history is no
longer observable. Multiple SELECTs can see a concurrent publication between them;
this is a point-in-time diagnostic, not a transactionally frozen audit. Use repeated
checks, [run logs](loader-runs.md), service/journal inspection and the existing TOI
and data audits for those separate questions. Alerts and service probes are not
installed by this command.
