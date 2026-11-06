import copy
from itertools import chain
from django.core.files.base import ContentFile

import requests
from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

from players.models import Goalie, Skater, Team
from players import nhl_http, season_loading
from players.season_stats import GOALIE, SKATER
from . import upd_pls

PLAYER_ENDPOINT_URL = "https://api-web.nhle.com/v1/player/{}/landing"
STATS_REST_SKATER_URL = "https://api.nhle.com/stats/rest/en/skater/{}"
STATS_REST_GOALIE_URL = "https://api.nhle.com/stats/rest/en/goalie/{}"
PLAYERS_PICS_DIR = "players_pics"

INCH_TO_FEET_COEFFICIENT = 12
POSITION_CODES = {
    "G": "Goalie",
    "D": "Defenseman",
    "L": "Left winger",
    "C": "Center",
    "R": "Right winger",
}
WINGERS_POSITION_CODES = ["L", "R", "W"]
REGULAR_SEASON_CODE = 2
NHL_LEAGUE_CODE = "NHL"
SKATER_REPORT_REALTIME = "realtime"
SKATER_REPORT_FACEOFF_WINS = "faceoffwins"
SKATER_REPORT_TIME_ON_ICE = "timeonice"
GOALIE_REPORT_SUMMARY = "summary"
STATS_REST_TIMEOUT = 10
STATS_REST_LIMIT = 250
CAREER_ENRICHMENT_TOTALS = "totals"
CAREER_ENRICHMENT_AVERAGES = "averages"
CURRENT_SEASON_STATS_FIELD_MAP = {
    "gamesPlayed": "games",
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "plusMinus": "plus_minus",
    "pim": "penalty_min",
    "shots": "shots",
    "hits": "hits",
    "blocked": "blocks",
    "faceoffsWon": "faceoff_wins",
    "powerPlayPoints": "pp_points",
    "shorthandedPoints": "sh_points",
    "avgToi": "time_on_ice",
    "powerPlayTimeOnIce": "time_on_ice_pp",
    "shortHandedTimeOnIce": "time_on_ice_sh",
}
CURRENT_SEASON_AVG_FIELD_MAP = {
    "gamesPlayed": "games",
    "goals": "goals_avg",
    "assists": "assists_avg",
    "points": "points_avg",
    "plusMinus": "plus_minus_avg",
    "pim": "penalty_min_avg",
    "shots": "shots_avg",
    "hits": "hits_avg",
    "blocked": "blocks_avg",
    "faceoffsWon": "faceoff_wins_avg",
    "powerPlayPoints": "pp_points_avg",
    "shorthandedPoints": "sh_points_avg",
    "avgToi": "time_on_ice",
    "powerPlayTimeOnIce": "time_on_ice_pp",
    "shortHandedTimeOnIce": "time_on_ice_sh",
}
GOALIE_CURRENT_SEASON_STATS_FIELD_MAP = {
    "gamesPlayed": "games",
    "wins": "wins",
    "losses": "losses",
    "otLosses": "ot_losses",
    "goalsAgainstAvg": "goals_against_av",
    "savePctg": "saves_perc",
    "saves": "saves",
    "shutouts": "shotouts",
}

TEAM_ABBR_FROM_NAME = {
    "Anaheim Ducks": "ANA",
    "Arizona Coyotes": "ARI",
    "Atlanta Thrashers": "ATL",
    "Boston Bruins": "BOS",
    "Buffalo Sabres": "BUF",
    "Calgary Flames": "CGY",
    "Carolina Hurricanes": "CAR",
    "Chicago Blackhawks": "CHI",
    "Colorado Avalanche": "COL",
    "Columbus Blue Jackets": "CBJ",
    "Dallas Stars": "DAL",
    "Detroit Red Wings": "DET",
    "Edmonton Oilers": "EDM",
    "Florida Panthers": "FLA",
    "Los Angeles Kings": "LAK",
    "Minnesota Wild": "MIN",
    "Montréal Canadiens": "MTL",
    "Nashville Predators": "NSH",
    "New Jersey Devils": "NJD",
    "New York Islanders": "NYI",
    "New York Rangers": "NYR",
    "Ottawa Senators": "OTT",
    "Philadelphia Flyers": "PHI",
    "Phoenix Coyotes": "PHO",
    "Pittsburgh Penguins": "PIT",
    "San Jose Sharks": "SJS",
    "Seattle Kraken": "SEA",
    "St. Louis Blues": "STL",
    "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR",
    "Vancouver Canucks": "VAN",
    "Vegas Golden Knights": "VGK",
    "Washington Capitals": "WSH",
    "Winnipeg Jets": "WPG",
}


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            choices=["full", "current"],
            default="full",
            help="Choose update mode: full (default) or current",
        )

    def handle(self, *args, **options):
        mode = options.get("mode", "full")
        if mode == "current":
            return run_current_mode()

        return run_full_mode()


def run_full_mode():
    players = get_all_players()

    with requests.Session() as session:
        for player in tqdm(players):
            print(f"\n Uploading from {player.name} page")
            data = get_response(player.nhl_id, session).json()
            import_player(data, player, session)


def run_current_mode():
    players = get_all_players()
    season = upd_pls.get_season_id()
    team_ids = dict(Team.objects.values_list("abbr", "nhl_id"))

    with requests.Session() as session:
        reports = {
            player_type: season_loading.fetch_reports(player_type, session, season)
            for player_type in (GOALIE, SKATER)
        }
        for player in tqdm(players):
            player_type = SKATER if isinstance(player, Skater) else GOALIE
            fresh = season_loading.assemble_player_rows(
                reports[player_type], player_type, player.nhl_id, team_ids, session
            )
            if player_type == SKATER:
                apply_current_mode_to_skater(player, session, season, team_ids, fresh)
            else:
                apply_current_mode_to_goalie(player, session, season, team_ids, fresh)


def get_all_players():
    return list(chain(Goalie.objects.all(), Skater.objects.all()))


def apply_current_mode_to_skater(player, session=None, season=None, team_ids=None, fresh=None):
    updates = get_current_mode_updates_for_skater(player, session, season, team_ids, fresh)
    for field, value in updates.items():
        setattr(player, field, value)

    if updates:
        player.save(update_fields=list(updates.keys()))


def apply_current_mode_to_goalie(player, session=None, season=None, team_ids=None, fresh=None):
    updates = get_current_mode_updates_for_goalie(player, session, season, team_ids, fresh)
    for field, value in updates.items():
        setattr(player, field, value)

    if updates:
        player.save(update_fields=list(updates.keys()))


def get_report_season_rows(player, player_type, session=None, season=None, team_ids=None):
    if team_ids is None:
        team_ids = dict(Team.objects.values_list("abbr", "nhl_id"))
    return season_loading.fetch_player_rows(player.nhl_id, player_type, team_ids, session, season)


def get_current_mode_updates_for_skater(
    player, session=None, season=None, team_ids=None, fresh=None
):
    season = season or upd_pls.get_season_id()
    if fresh is None:
        fresh = get_report_season_rows(player, SKATER, session, season, team_ids)
    updates = season_loading.season_row_updates(player, fresh, SKATER)
    career_stats = copy.deepcopy(player.career_stats or {})
    career_stats_avg = copy.deepcopy(player.career_stats_avg or {})
    career_enrichment = get_skater_career_enrichment(player, session)
    career_stats = enrich_career_stats(career_stats, career_enrichment, CAREER_ENRICHMENT_TOTALS)
    if not career_stats_avg and career_stats:
        career_stats_avg = get_career_average_stats(copy.deepcopy(career_stats))
    career_stats_avg = enrich_career_stats(
        career_stats_avg, career_enrichment, CAREER_ENRICHMENT_AVERAGES, overwrite_existing=True
    )
    updates.update({"career_stats": career_stats, "career_stats_avg": career_stats_avg})
    return updates


def get_current_mode_updates_for_goalie(
    player, session=None, season=None, team_ids=None, fresh=None
):
    season = season or upd_pls.get_season_id()
    if fresh is None:
        fresh = get_report_season_rows(player, GOALIE, session, season, team_ids)
    updates = season_loading.season_row_updates(player, fresh, GOALIE)
    career_enrichment = get_goalie_career_enrichment(player, session)
    updates["career_stats"] = enrich_career_stats(
        copy.deepcopy(player.career_stats or {}),
        career_enrichment,
        CAREER_ENRICHMENT_TOTALS,
        overwrite_existing=True,
    )
    return updates


def import_player(data, player, session=None):
    image_name = f"{player.slug}.png"

    if upd_pls.pic_missing(image_name, player.image, PLAYERS_PICS_DIR):
        upload_profile_image(data["headshot"], player, image_name)

    defaults = {
        "first_name": data["firstName"]["default"],
        "height": inches_to_feet(int(data["heightInInches"])),
        "height_cm": data["heightInCentimeters"],
        "weight": data["weightInPounds"],
        "weight_kg": data["weightInKilograms"],
        "pl_number": data.get("sweaterNumber"),
        "position_abbr": get_position_abbreviation(data["position"]),
        "position_name": POSITION_CODES[data["position"]],
    }

    defaults["career_stats"] = data["careerTotals"]["regularSeason"]
    player_type = GOALIE if data["position"] == "G" else SKATER
    fresh = get_report_season_rows(player, player_type, session)
    defaults.update(season_loading.season_row_updates(player, fresh, player_type))
    if player_type == SKATER:
        career_enrichment = get_skater_career_enrichment(player, session)
        defaults["career_stats"] = enrich_career_stats(
            defaults["career_stats"], career_enrichment, CAREER_ENRICHMENT_TOTALS
        )
        defaults["career_stats_avg"] = enrich_career_stats(
            get_career_average_stats(copy.deepcopy(defaults["career_stats"])),
            career_enrichment,
            CAREER_ENRICHMENT_AVERAGES,
            overwrite_existing=True,
        )
        Skater.objects.update_or_create(nhl_id=player.nhl_id, defaults=defaults)
    else:
        totals = defaults["career_stats"]
        if totals.get("shotsAgainst") is not None and totals.get("goalsAgainst") is not None:
            totals["saves"] = totals["shotsAgainst"] - totals["goalsAgainst"]
        Goalie.objects.update_or_create(nhl_id=player.nhl_id, defaults=defaults)


def upload_profile_image(image_url, player_object, image_name):
    with nhl_http.required_get(image_url, context="player profile image") as response:
        player_object.image.save(name=image_name, content=ContentFile(response.content))


def get_response(nhl_id, session=None):
    return nhl_http.required_get(
        PLAYER_ENDPOINT_URL.format(nhl_id), session=session, context=f"player {nhl_id} landing"
    )


def get_career_average_stats(career_stats_average):
    career_stats_average["goals"] = get_average("goals", career_stats_average)
    career_stats_average["assists"] = get_average("assists", career_stats_average)
    career_stats_average["points"] = get_average("points", career_stats_average)
    career_stats_average["powerPlayPoints"] = get_average("powerPlayPoints", career_stats_average)
    career_stats_average["shorthandedPoints"] = get_average(
        "shorthandedPoints", career_stats_average
    )
    career_stats_average["plusMinus"] = get_average("plusMinus", career_stats_average)
    career_stats_average["shots"] = get_average("shots", career_stats_average)
    career_stats_average["pim"] = get_average("pim", career_stats_average)

    return career_stats_average


def get_season_by_season_stats(seasons_data, position_code):
    nhl_seasons = []
    for season in seasons_data:
        if (
            season["leagueAbbrev"] == NHL_LEAGUE_CODE
            and season["gameTypeId"] == REGULAR_SEASON_CODE
        ):
            season["season"] = format_season(str(season["season"]))
            try:
                season["teamAbbr"] = TEAM_ABBR_FROM_NAME[season["teamName"]["default"]]
            except KeyError as e:
                print(e)

            if position_code == list(POSITION_CODES.keys())[0]:
                season["saves"] = season["shotsAgainst"] - season["goalsAgainst"]

            nhl_seasons.append(season)

    return nhl_seasons


def get_season_by_season_average_stats(nhl_regular_seasons_data):
    for season in nhl_regular_seasons_data:
        season["goals"] = get_average("goals", season)
        season["assists"] = get_average("assists", season)
        season["points"] = get_average("points", season)
        season["powerPlayPoints"] = get_average("powerPlayPoints", season)
        season["shorthandedPoints"] = get_average("shorthandedPoints", season)
        season["plusMinus"] = get_average("plusMinus", season)
        season["shots"] = get_average("shots", season)
        season["pim"] = get_average("pim", season)

    return nhl_regular_seasons_data


def get_average(stat, stats_tot_avg):
    return safe_per_game(stats_tot_avg.get(stat), stats_tot_avg.get("gamesPlayed"))


def get_position_abbreviation(position_code):
    if position_code in WINGERS_POSITION_CODES:
        return position_code + WINGERS_POSITION_CODES[2]
    else:
        return position_code


def get_skater_season_enrichment(player, session=None):
    season_enrichment = {}
    current_season = get_player_current_season(player)

    realtime_rows = get_stats_rest_rows(SKATER_REPORT_REALTIME, player.nhl_id, session)
    faceoff_rows = get_stats_rest_rows(SKATER_REPORT_FACEOFF_WINS, player.nhl_id, session)
    toi_rows = get_stats_rest_rows(SKATER_REPORT_TIME_ON_ICE, player.nhl_id, session)

    for row in realtime_rows:
        season = format_season(str(row.get("seasonId")))
        if season == current_season:
            continue

        games_played = row.get("gamesPlayed") or 0
        add_season_enrichment(
            season_enrichment,
            season,
            "totals",
            {
                "hits": row.get("hits"),
                "blocked": row.get("blockedShots"),
            },
        )
        add_season_enrichment(
            season_enrichment,
            season,
            "averages",
            {
                "hits": safe_per_game(row.get("hits"), games_played),
                "blocked": safe_per_game(row.get("blockedShots"), games_played),
            },
        )

    for row in faceoff_rows:
        season = format_season(str(row.get("seasonId")))
        if season == current_season:
            continue

        games_played = row.get("gamesPlayed") or 0
        total_faceoff_wins = row.get("totalFaceoffWins")
        add_season_enrichment(
            season_enrichment,
            season,
            "totals",
            {"faceoffsWon": total_faceoff_wins},
        )
        add_season_enrichment(
            season_enrichment,
            season,
            "averages",
            {"faceoffsWon": safe_per_game(total_faceoff_wins, games_played)},
        )

    for row in toi_rows:
        season = format_season(str(row.get("seasonId")))
        if season == current_season:
            continue

        pp_toi = time_from_seconds_value(row.get("ppTimeOnIcePerGame"))
        sh_toi = time_from_seconds_value(row.get("shTimeOnIcePerGame"))
        add_season_enrichment(
            season_enrichment,
            season,
            "totals",
            {
                "powerPlayTimeOnIce": pp_toi,
                "shortHandedTimeOnIce": sh_toi,
            },
        )
        add_season_enrichment(
            season_enrichment,
            season,
            "averages",
            {
                "powerPlayTimeOnIce": pp_toi,
                "shortHandedTimeOnIce": sh_toi,
            },
        )

    return season_enrichment


def get_skater_career_enrichment(player, session=None):
    career_enrichment = {
        CAREER_ENRICHMENT_TOTALS: {},
        CAREER_ENRICHMENT_AVERAGES: {},
    }

    realtime_rows = get_stats_rest_rows(
        SKATER_REPORT_REALTIME,
        player.nhl_id,
        session,
        aggregate=True,
    )
    faceoff_rows = get_stats_rest_rows(
        SKATER_REPORT_FACEOFF_WINS,
        player.nhl_id,
        session,
        aggregate=True,
    )
    toi_rows = get_stats_rest_rows(
        SKATER_REPORT_TIME_ON_ICE,
        player.nhl_id,
        session,
        aggregate=True,
    )

    if realtime_rows:
        row = realtime_rows[0]
        games_played = row.get("gamesPlayed") or 0
        career_enrichment[CAREER_ENRICHMENT_TOTALS].update(
            {
                "hits": row.get("hits"),
                "blocked": row.get("blockedShots"),
            }
        )
        career_enrichment[CAREER_ENRICHMENT_AVERAGES].update(
            {
                "hits": safe_per_game(row.get("hits"), games_played),
                "blocked": safe_per_game(row.get("blockedShots"), games_played),
            }
        )

    if faceoff_rows:
        row = faceoff_rows[0]
        games_played = row.get("gamesPlayed") or 0
        total_faceoff_wins = row.get("totalFaceoffWins")
        career_enrichment[CAREER_ENRICHMENT_TOTALS]["faceoffsWon"] = total_faceoff_wins
        career_enrichment[CAREER_ENRICHMENT_AVERAGES]["faceoffsWon"] = safe_per_game(
            total_faceoff_wins,
            games_played,
        )

    if toi_rows:
        row = toi_rows[0]
        career_enrichment[CAREER_ENRICHMENT_TOTALS].update(
            {
                "powerPlayTimeOnIcePerGame": time_from_seconds_value(row.get("ppTimeOnIcePerGame")),
                "shortHandedTimeOnIcePerGame": time_from_seconds_value(
                    row.get("shTimeOnIcePerGame")
                ),
            }
        )
        career_enrichment[CAREER_ENRICHMENT_AVERAGES].update(
            {
                "powerPlayTimeOnIcePerGame": time_from_seconds_value(row.get("ppTimeOnIcePerGame")),
                "shortHandedTimeOnIcePerGame": time_from_seconds_value(
                    row.get("shTimeOnIcePerGame")
                ),
            }
        )

    return career_enrichment


def get_goalie_career_enrichment(player, session=None):
    career_enrichment = {
        CAREER_ENRICHMENT_TOTALS: {},
    }

    summary_rows = get_goalie_stats_rest_rows(
        GOALIE_REPORT_SUMMARY,
        player.nhl_id,
        session,
        aggregate=True,
    )
    if not summary_rows:
        return career_enrichment

    row = summary_rows[0]
    career_enrichment[CAREER_ENRICHMENT_TOTALS].update(
        {
            "gamesPlayed": row.get("gamesPlayed"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "otLosses": row.get("otLosses"),
            "goalsAgainstAvg": row.get("goalsAgainstAverage"),
            "savePctg": row.get("savePct"),
            "saves": row.get("saves"),
            "shutouts": row.get("shutouts"),
        }
    )

    return career_enrichment


def get_stats_rest_rows(report_type, player_id, session=None, aggregate=False):
    client = session or requests
    params = {
        "isAggregate": "true" if aggregate else "false",
        "isGame": "false",
        "limit": STATS_REST_LIMIT,
        "start": 0,
        "cayenneExp": f"gameTypeId={REGULAR_SEASON_CODE} and playerId={player_id}",
    }

    response = nhl_http.optional_get(
        STATS_REST_SKATER_URL.format(report_type),
        session=client,
        params=params,
        timeout=STATS_REST_TIMEOUT,
        context=f"skater career {report_type} for {player_id}",
    )
    if response is None:
        return []

    return checked_stats_rest_rows(response, report_type, player_id)


def get_goalie_stats_rest_rows(report_type, player_id, session=None, aggregate=False):
    client = session or requests
    params = {
        "isAggregate": "true" if aggregate else "false",
        "isGame": "false",
        "limit": STATS_REST_LIMIT,
        "start": 0,
        "cayenneExp": f"gameTypeId={REGULAR_SEASON_CODE} and playerId={player_id}",
    }

    response = nhl_http.optional_get(
        STATS_REST_GOALIE_URL.format(report_type),
        session=client,
        params=params,
        timeout=STATS_REST_TIMEOUT,
        context=f"goalie career {report_type} for {player_id}",
    )
    if response is None:
        return []

    return checked_stats_rest_rows(response, report_type, player_id)


def checked_stats_rest_rows(response, report_type, player_id):
    """A malformed optional report must not masquerade as valid empty data."""
    try:
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Expected a JSON object with a data list")
        if any(not isinstance(row, dict) for row in payload["data"]):
            raise ValueError("Expected report rows to be JSON objects")
    except ValueError as error:
        raise CommandError(
            f"Invalid career report {report_type} for player {player_id}: {error}"
        ) from error
    return payload["data"]


def get_player_current_season(player):
    stats_season_id = getattr(player, "stats_season_id", None)
    if not stats_season_id:
        return None

    return format_season(str(stats_season_id))


def add_season_enrichment(season_enrichment, season, bucket, values):
    season_enrichment.setdefault(season, {})
    season_enrichment[season].setdefault(bucket, {})
    season_enrichment[season][bucket].update(values)


def safe_per_game(value, games_played):
    if value is None or not games_played:
        return None

    return round(value / games_played, 2)


def time_from_seconds_value(seconds):
    if seconds is None:
        return None

    return upd_pls.time_from_sec(seconds)


def enrich_season_stats_from_enrichment(
    seasons_stats,
    season_enrichment,
    bucket,
    overwrite_existing=False,
):
    for season in seasons_stats:
        season_key = season.get("season")
        if season_key not in season_enrichment:
            continue

        for field, value in season_enrichment[season_key].get(bucket, {}).items():
            if value in [None, ""]:
                continue

            if not overwrite_existing and season.get(field) not in [None, ""]:
                continue

            season[field] = value

    return seasons_stats


def enrich_career_stats(career_stats, career_enrichment, bucket, overwrite_existing=False):
    values = (career_enrichment or {}).get(bucket, {})
    for field, value in values.items():
        if value in [None, ""]:
            continue

        if not overwrite_existing and career_stats.get(field) not in [None, ""]:
            continue

        career_stats[field] = value

    return career_stats


def enrich_current_season_stats_from_player(
    seasons_stats,
    player,
    field_map,
    overwrite_existing=False,
):
    stats_season_id = getattr(player, "stats_season_id", None)
    if not stats_season_id:
        return seasons_stats

    current_season = format_season(str(stats_season_id))
    for season in seasons_stats:
        if season.get("season") != current_season:
            continue

        for season_field, player_field in field_map.items():
            if not overwrite_existing and season.get(season_field) not in [None, ""]:
                continue

            player_value = getattr(player, player_field, None)
            if player_value in [None, ""]:
                continue

            season[season_field] = player_value

        break

    return seasons_stats


def inches_to_feet(height):
    feet, inches = divmod(height, INCH_TO_FEET_COEFFICIENT)
    return f"{feet}'{inches}\""


def format_season(season):
    return f"{season[:4]}-{season[6:]}"
