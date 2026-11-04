"""Fetch and assemble season rows before publishing any player statistics."""

from collections import Counter
from copy import deepcopy

import requests
from django.core.management.base import CommandError

from .season_stats import (
    GOALIE,
    SKATER,
    SKATER_COUNT_FIELDS,
    SKATER_TIME_FIELDS,
    normalize_season_id,
    read_season_stats,
)


REPORT_URL = "https://api.nhle.com/stats/rest/en/{}/{}"
TEAM_REGISTRY_URL = "https://api.nhle.com/stats/rest/en/team"
REPORT_LIMIT = 100
REPORT_TIMEOUT = 10
REPORT_ATTEMPTS = 3
REGULAR_SEASON = 2
SUMMARY = "summary"
BIOS = "bios"
REALTIME = "realtime"
FACEOFFS = "faceoffwins"
TIME_ON_ICE = "timeonice"
REPORTS = {SKATER: (SUMMARY, REALTIME, FACEOFFS, TIME_ON_ICE), GOALIE: (SUMMARY,)}
SUMMARY_SKATER_FIELDS = {
    "gamesPlayed": "gamesPlayed",
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "plusMinus": "plusMinus",
    "pim": "penaltyMinutes",
    "shots": "shots",
    "powerPlayPoints": "ppPoints",
    "shorthandedPoints": "shPoints",
}
SUMMARY_GOALIE_FIELDS = {
    "gamesPlayed": "gamesPlayed",
    "wins": "wins",
    "losses": "losses",
    "otLosses": "otLosses",
    "goalsAgainstAvg": "goalsAgainstAverage",
    "savePctg": "savePct",
    "saves": "saves",
    "shutouts": "shutouts",
    "shotsAgainst": "shotsAgainst",
    "goalsAgainst": "goalsAgainst",
}
SECONDS_PER_MINUTE = 60


def fetch_report(report, player_type, session=None, season=None, player_id=None, team_id=None):
    """Fetch all pages or raise; a failed request must never resemble empty data."""
    client = session or requests
    expression = ["gameTypeId={}".format(REGULAR_SEASON)]
    if season is not None:
        expression.append("seasonId={}".format(normalize_season_id(season)))
    if player_id is not None:
        expression.append("playerId={}".format(int(player_id)))
    if team_id is not None:
        expression.append("teamId={}".format(int(team_id)))
    params = {
        "isAggregate": "false",
        "isGame": "false",
        "limit": REPORT_LIMIT,
        "start": 0,
        "cayenneExp": " and ".join(expression),
        "sort": '[{"property":"playerId","direction":"ASC"},{"property":"seasonId","direction":"ASC"}]',
    }
    if report == BIOS:
        params["sort"] = '[{"property":"playerId","direction":"ASC"}]'
    rows = _fetch_pages(
        REPORT_URL.format(player_type, report), params, client, player_type + " " + report
    )
    for row in rows:
        if player_id is not None and row.get("playerId") != player_id:
            raise CommandError("Report returned a different player than requested")
        if season is not None and report != BIOS:
            if normalize_season_id(row.get("seasonId")) != normalize_season_id(season):
                raise CommandError("Report returned a different season than requested")
    return rows


def _fetch_pages(url, params, client, label):
    rows = []
    while True:
        for attempt in range(REPORT_ATTEMPTS):
            try:
                response = client.get(url, params=dict(params), timeout=REPORT_TIMEOUT)
                response.raise_for_status()
                payload = response.json()
                if (
                    not isinstance(payload, dict)
                    or not isinstance(payload.get("data"), list)
                    or not isinstance(payload.get("total"), int)
                    or payload["total"] < 0
                    or any(not isinstance(row, dict) for row in payload["data"])
                ):
                    raise ValueError("Expected a report data array and total count")
                break
            except (requests.RequestException, ValueError) as error:
                if attempt == REPORT_ATTEMPTS - 1:
                    raise CommandError(
                        "Failed {} report at start={}: {}".format(label, params["start"], error)
                    ) from error
        page = payload["data"]
        rows.extend(page)
        if len(rows) > payload["total"]:
            raise CommandError("Report contains more rows than its declared total")
        if len(rows) == payload["total"]:
            return rows
        if not page:
            raise CommandError("Report pagination ended before its declared total")
        params["start"] += len(page)


def fetch_team_ids(session=None):
    rows = _fetch_pages(
        TEAM_REGISTRY_URL,
        {"limit": REPORT_LIMIT, "start": 0, "sort": '[{"property":"id","direction":"ASC"}]'},
        session or requests,
        "team registry",
    )
    candidates = {}
    for row in rows:
        for key in ("triCode", "rawTricode"):
            if row.get(key) and row.get("id") is not None:
                candidates.setdefault(row[key], set()).add(row["id"])
    return {
        team: next(iter(ids)) if len(ids) == 1 else tuple(sorted(ids))
        for team, ids in candidates.items()
    }


def fetch_reports(player_type, session=None, season=None, player_id=None, team_id=None):
    return {
        report: fetch_report(report, player_type, session, season, player_id, team_id)
        for report in REPORTS[player_type]
    }


def _report_row(reports, report, player_id, season):
    matches = [
        row
        for row in reports.get(report, [])
        if row.get("playerId") == player_id and normalize_season_id(row.get("seasonId")) == season
    ]
    if len(matches) > 1:
        raise CommandError(
            "Ambiguous {} rows for player {}, season {}".format(report, player_id, season)
        )
    return matches[0] if matches else {}


def _time(seconds):
    if seconds is None:
        return None
    minutes, seconds = divmod(int(seconds), SECONDS_PER_MINUTE)
    return "{:02d}:{:02d}".format(minutes, seconds)


def _teams(row):
    return sorted(
        set(team.strip() for team in (row.get("teamAbbrevs") or "").split(",") if team.strip())
    )


def _assemble_row(reports, player_type, player_id, season, team_abbr):
    summary = _report_row(reports, SUMMARY, player_id, season)
    if not summary:
        return None
    games = summary.get("gamesPlayed")
    if not isinstance(games, int) or games < 0:
        raise CommandError("Summary has invalid gamesPlayed for player {}".format(player_id))
    fields = SUMMARY_SKATER_FIELDS if player_type == SKATER else SUMMARY_GOALIE_FIELDS
    row = {target: summary.get(source) for target, source in fields.items()}
    row.update(
        {
            "season": "{}-{}".format(season[:4], season[-2:]),
            "leagueAbbrev": "NHL",
            "gameTypeId": REGULAR_SEASON,
            "teamAbbr": team_abbr,
        }
    )
    if player_type == SKATER:
        realtime = _report_row(reports, REALTIME, player_id, season)
        faceoffs = _report_row(reports, FACEOFFS, player_id, season)
        toi = _report_row(reports, TIME_ON_ICE, player_id, season)
        for report in (realtime, faceoffs, toi):
            if report and report.get("gamesPlayed") != games:
                raise CommandError(
                    "Reports disagree on gamesPlayed for player {}".format(player_id)
                )
            if report and _teams(report) != _teams(summary):
                raise CommandError(
                    "Reports disagree on team splits for player {}".format(player_id)
                )
        row.update(
            {
                "hits": realtime.get("hits"),
                "blocked": realtime.get("blockedShots"),
                "faceoffsWon": faceoffs.get("totalFaceoffWins"),
                "avgToi": _time(toi.get("timeOnIcePerGame", summary.get("timeOnIcePerGame"))),
                "powerPlayTimeOnIce": _time(toi.get("ppTimeOnIcePerGame")),
                "shortHandedTimeOnIce": _time(toi.get("shTimeOnIcePerGame")),
            }
        )
    elif (
        row["saves"] is None and row["shotsAgainst"] is not None and row["goalsAgainst"] is not None
    ):
        row["saves"] = row["shotsAgainst"] - row["goalsAgainst"]
    return row


def _fetch_team_reports(player_type, player_id, season, team, team_ids, session):
    """Resolve reused abbreviations through player/season-scoped report evidence."""
    attempted = set()
    matches = []

    def try_candidates():
        value = team_ids[team]
        candidates = value if isinstance(value, tuple) else (value,)
        for team_id in candidates:
            if team_id in attempted:
                continue
            attempted.add(team_id)
            scoped = fetch_reports(player_type, session, season, player_id, team_id)
            if _report_row(scoped, SUMMARY, player_id, season):
                matches.append(scoped)

    try_candidates()
    if not matches:
        # Current metadata can point at a successor team (e.g. Utah Mammoth),
        # while a historical contribution belongs to an earlier team ID.
        # Keep all registry IDs; do not replace them with a season-specific ID.
        team_ids.update(fetch_team_ids(session))
        try_candidates()
    if len(matches) > 1:
        raise CommandError(
            "Ambiguous {} team IDs for player {}, season {}".format(team, player_id, season)
        )
    return matches[0] if matches else {}


def assemble_player_rows(reports, player_type, player_id, team_ids, session=None):
    """Keep combined results separate from team-scoped requests for traded players."""
    result = []
    summaries = [row for row in reports[SUMMARY] if row.get("playerId") == player_id]
    for summary in summaries:
        split_start = len(result)
        season = normalize_season_id(summary.get("seasonId"))
        teams = _teams(summary)
        if not teams:
            raise CommandError("Summary has no team identity for player {}".format(player_id))
        result.append(
            _assemble_row(
                reports, player_type, player_id, season, teams[0] if len(teams) == 1 else "TOT"
            )
        )
        if len(teams) > 1:
            if any(team not in team_ids for team in teams):
                team_ids.update(fetch_team_ids(session))
            for team in teams:
                if team not in team_ids:
                    raise CommandError("Unknown historical team {}".format(team))
                scoped = _fetch_team_reports(
                    player_type, player_id, season, team, team_ids, session
                )
                scoped_summary = _report_row(scoped, SUMMARY, player_id, season)
                # NHL reports can retain the full season's teamAbbrevs even
                # when teamId correctly scopes the numeric statistics. Use the
                # requested team for the saved row; reconcile counts below.
                scoped_teams = set(_teams(scoped_summary))
                if team not in scoped_teams or not scoped_teams.issubset(teams):
                    raise CommandError(
                        "Missing or invalid {} split for player {}, season {}".format(
                            team, player_id, season
                        )
                    )
                result.append(_assemble_row(scoped, player_type, player_id, season, team))
            combined = result[split_start]
            splits = result[split_start + 1 :]
            fields = SUMMARY_SKATER_FIELDS if player_type == SKATER else SUMMARY_GOALIE_FIELDS
            rate_keys = {"goalsAgainstAvg", "savePctg"}
            for key in fields:
                if key not in rate_keys and combined.get(key) is not None:
                    values = [row.get(key) for row in splits]
                    if all(value is not None for value in values) and sum(values) != combined[key]:
                        raise CommandError(
                            "Team splits disagree with combined {} for player {}".format(
                                key, player_id
                            )
                        )
    return result


def fetch_player_rows(player_id, player_type, team_ids, session=None, season=None):
    reports = fetch_reports(player_type, session, season, player_id)
    return assemble_player_rows(reports, player_type, player_id, team_ids, session)


def merge_season_rows(existing, fresh):
    """Replace refreshed seasons as units; leave untouched history byte-for-byte."""
    fresh_seasons = {normalize_season_id(row["season"]) for row in fresh}
    kept = [
        deepcopy(row)
        for row in (existing or [])
        if normalize_season_id(row["season"]) not in fresh_seasons
    ]
    return kept + deepcopy(fresh)


def season_row_updates(player, fresh, player_type):
    """Prepare SBS, averages, and snapshot columns for one atomic database save."""
    if not fresh:
        return {}
    rows = merge_season_rows(player.sbs_stats, fresh)
    counts = Counter(row["season"] for row in rows if row.get("teamAbbr") != "TOT")
    updates = {
        "sbs_stats": rows,
        "multiteams_seasons": {season: count for season, count in counts.items() if count > 1},
    }
    if player_type == SKATER:
        averaged = []
        for row in fresh:
            stats = read_season_stats([row], row["season"], player_type=SKATER)
            copy = deepcopy(row)
            for field, key in SKATER_COUNT_FIELDS.items():
                if field != "games":
                    copy[key] = stats.averages[field + "_avg"]
            averaged.append(copy)
        updates["sbs_stats_avg"] = merge_season_rows(player.sbs_stats_avg, averaged)

    latest = max(normalize_season_id(row["season"]) for row in fresh)
    old_snapshot_season = getattr(player, "stats_season_id", None)
    if old_snapshot_season and normalize_season_id(old_snapshot_season) > latest:
        return updates
    stats = read_season_stats(rows, latest, player_type=player_type)
    updates.update(stats.totals)
    if stats.averages is not None:
        updates.update(stats.averages)
        # These legacy cache columns are NOT NULL; SBS keeps unknown times as null.
        for field in SKATER_TIME_FIELDS:
            updates[field] = updates[field] or ""
    else:
        # The legacy shutout cache is NOT NULL; the SBS value remains nullable.
        updates["shotouts"] = updates["shotouts"] or 0
    updates["stats_season_id"] = latest
    return updates
