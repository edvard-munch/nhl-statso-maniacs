import logging
import os
import urllib
from datetime import date

import requests
from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date
from players.models import Goalie, Skater, Team
from tqdm import tqdm

from players import season_loading
from players.season_stats import GOALIE, SKATER

from . import upd_tms
from . import upd_pls_tot

DEFAULT_SEASON = "20252026"
URL_SCHEDULE_CALENDAR_NOW = "https://api-web.nhle.com/v1/schedule-calendar/now"

URL_PLAYERS = "https://api.nhle.com/stats/rest/en/{}/{}"
FLAGS_DIR = "flags"

PL_TYPE1 = "goalie"
PL_TYPE2 = "skater"
REP_TYPE1 = "bios"
REP_TYPE2 = "summary"
REP_TYPE3 = "realtime"
REP_TYPE4 = "timeonice"
REP_TYPE5 = "faceoffwins"
POS_CODE_KEY = "positionCode"

PLAYERS_PER_PAGE = 100
START_INDEX = 0
TODAY = date.today()
REQUEST_PARAMS = {
    "isAggregate": "false",
    "isGame": "false",
    "limit": PLAYERS_PER_PAGE,
    "start": 0,
    "cayenneExp": f"gameTypeId=2 and seasonId={DEFAULT_SEASON}",
    "sort": """[{"property":"lastName","direction":"ASC_CI"},
                {"property":"playerId","direction":"ASC_CI"}]""",
}
TIMEOUT = 3
logger = logging.getLogger("django")
UNKNOWN_COUNTRY_CODES = set()

# Find a table with this, or transfer the dict to the external file
COUNTRIES = {
    "RUS": "Russia",
    "CAN": "Canada",
    "USA": "USA",
    "CZE": "Czech Republic",
    "CSK": "Czech Republic",
    "CHE": "Switzerland",
    "SWE": "Sweden",
    "FIN": "Finland",
    "DEU": "Germany",
    "DNK": "Denmark",
    "AUT": "Austria",
    "FRA": "France",
    "ITA": "Italia",
    "NOR": "Norway",
    "LVA": "Latvia",
    "SVN": "Slovenia",
    "SVK": "Slovakia",
    "NLD": "Netherlands",
    "AUS": "Australia",
    "GBR": "Great Britain",
    "KAZ": "Kazachstan",
    "BGR": "Bulgaria",
    "EST": "Estonia",
    "UKR": "Ukraine",
    "UZB": "Uzbekistan",
    "BLR": "Belarus",
    "POL": "Poland",
    None: "",
}


class Command(BaseCommand):
    def handle(self, *args, **options):
        UNKNOWN_COUNTRY_CODES.clear()
        season = get_season_id()
        logger.info("upd_pls using seasonId=%s", season)
        team_ids = dict(Team.objects.values_list("abbr", "nhl_id"))
        staged = []
        with requests.Session() as session:
            for player_type in (GOALIE, SKATER):
                bios = season_loading.fetch_report(
                    season_loading.BIOS, player_type, session, season
                )
                reports = season_loading.fetch_reports(player_type, session, season)
                bio_ids = [bio["playerId"] for bio in bios]
                summary_ids = {row["playerId"] for row in reports[season_loading.SUMMARY]}
                if len(set(bio_ids)) != len(bio_ids) or not summary_ids.issubset(bio_ids):
                    raise CommandError("Bios report does not cover summary players uniquely")
                for bio in bios:
                    fresh = season_loading.assemble_player_rows(
                        reports, player_type, bio["playerId"], team_ids, session
                    )
                    if fresh:
                        if bio["gamesPlayed"] != fresh[0]["gamesPlayed"]:
                            raise CommandError("Bios and summary disagree on gamesPlayed")
                        staged.append((player_type, bio, fresh))

        # All requests and validation finish before a season marker can be published.
        saved = []
        with transaction.atomic():
            for player_type, bio, fresh in tqdm(staged):
                saved.append(import_player(bio, fresh, player_type))
        for player in saved:
            flag_name = f"{player.nation_abbr}.jpg"
            if pic_missing(flag_name, player.nation_flag, FLAGS_DIR):
                upload_flag(player, flag_name)
        if UNKNOWN_COUNTRY_CODES:
            logger.warning(
                "Unknown country codes from NHL API in upd_pls: %s",
                ", ".join(sorted(UNKNOWN_COUNTRY_CODES)),
            )


def get_bio_defaults(player, player_type):
    birth_country = player.get("birthCountryCode")
    nationality = player.get("nationalityCode") or birth_country
    position = player.get(POS_CODE_KEY, "G" if player_type == GOALIE else "")
    defaults = {
        "name": get_char_field_value(
            player, "goalieFullName" if player_type == GOALIE else "skaterFullName"
        ),
        "last_name": get_char_field_value(player, "lastName"),
        "birth_date": parse_date(player["birthDate"]),
        "birth_city": get_char_field_value(player, "birthCity"),
        "birth_state": get_char_field_value(player, "birthStateProvinceCode"),
        "birth_country": get_country_name(birth_country),
        "birth_country_abbr": birth_country or "",
        "nation": get_country_name(nationality),
        "nation_abbr": nationality or "",
        "age": calculate_age(parse_date(player["birthDate"]), TODAY),
        "nhl_debut": upd_pls_tot.format_season(str(player["firstSeasonForGameType"])),
        "team": Team.objects.filter(abbr=player.get("currentTeamAbbrev")).first(),
        "position_abbr": upd_pls_tot.get_position_abbreviation(position),
        "position_name": upd_pls_tot.POSITION_CODES.get(position, ""),
    }
    if player.get("draftOverall"):
        defaults.update(
            {
                "draft_year": player.get("draftYear"),
                "draft_round": player.get("draftRound"),
                "draft_number": player["draftOverall"],
            }
        )
    return defaults


def import_player(bio, fresh, player_type):
    model = Skater if player_type == SKATER else Goalie
    player = model.objects.select_for_update().filter(nhl_id=bio["playerId"]).first()
    if player is None:
        player = model(nhl_id=bio["playerId"])
    defaults = get_bio_defaults(bio, player_type)
    defaults.update(season_loading.season_row_updates(player, fresh, player_type))
    for field, value in defaults.items():
        setattr(player, field, value)
    player.save()
    return player


def get_response(rep_type, pl_type, start_from_index):
    """
    Args:
      rep_type:
      pl_type:

    Returns:

    """
    print(pl_type, rep_type)

    url = URL_PLAYERS.format(pl_type, rep_type)
    params = REQUEST_PARAMS
    params["start"] = start_from_index

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        print(resp.url)
        return resp

    except requests.HTTPError as e:  # if Not fOUND
        print(e.code)
        print("Wrong endpoint or a problem with the connection!")
        return None
    except requests.exceptions.ReadTimeout:
        print("Timeout!")
        return None


def get_season_id():
    try:
        response = requests.get(URL_SCHEDULE_CALENDAR_NOW, timeout=TIMEOUT).json()
        season_ids = {
            str(team["seasonId"]) for team in response.get("teams", []) if team.get("seasonId")
        }

        if len(season_ids) == 1:
            return season_ids.pop()

        if season_ids:
            season_id = sorted(season_ids)[-1]
            logger.warning(
                "Multiple seasonId values from NHL schedule API (%s), using %s",
                ", ".join(sorted(season_ids)),
                season_id,
            )
            return season_id

    except requests.exceptions.RequestException as exc:
        logger.warning("Failed to autodetect seasonId from NHL API: %s", exc)

    logger.warning("Falling back to default seasonId=%s", DEFAULT_SEASON)
    return DEFAULT_SEASON


def calculate_age(born, today):
    # Using tuple comparison and a fact that True == 1 and False == 0
    no_birthday_this_year_yet = (today.month, today.day) < (born.month, born.day)
    return today.year - born.year - no_birthday_this_year_yet


def get_char_field_value(player, field):
    try:
        if player[field] is None:
            return ""
        else:
            return player[field]

    except KeyError:
        return ""


def get_num_field_value(player, field):
    if player[field] is None:
        player[field] = 0
    return player[field]


def get_country_name(country_code):
    if country_code in COUNTRIES:
        return COUNTRIES[country_code]

    if country_code not in UNKNOWN_COUNTRY_CODES:
        UNKNOWN_COUNTRY_CODES.add(country_code)
        logger.warning("Unknown country code from NHL API: %s", country_code)

    return country_code


def pic_missing(pic_name, field, directory):
    """

    Args:
      pic_name:
      field:
      dir:

    Returns:

    """
    path = os.path.join(settings.MEDIA_ROOT, directory, pic_name)
    # field.path != path should be unnecessary in production
    return not field or not os.path.isfile(path) or field.path != path


def upload_pic(directory, object_, img_name, url):
    """

    Args:
      object:
      img_name:
      url:

    Returns:

    """

    path = os.path.join(settings.MEDIA_ROOT, directory, img_name)

    if os.path.isfile(path):
        pic = File(open(path, "rb"))
        object_.image.save(name=img_name, content=pic)
    else:
        try:
            if directory == upd_tms.TEAMS_LOGOS_DIR:
                id_string = object_.abbr

            else:
                id_string = object_.nhl_id

            content = urllib.request.urlretrieve(url.format(id_string))

            pic = File(open(content[0], "rb"))
            object_.image.save(name=img_name, content=pic)

        except urllib.error.HTTPError:
            print(f"{object_.name} has no picture yet")

        except urllib.error.URLError:
            print("Request failed")


def upload_flag(player_obj, flag_name):
    """

    Args:
      player_obj:
      flag_name:

    Returns:

    """
    path_elements = [settings.MEDIA_ROOT, FLAGS_DIR, flag_name]
    abs_file_path = os.path.join(*path_elements)
    rel_file_path = os.path.join(*path_elements[1:])

    if os.path.isfile(abs_file_path):
        player_obj.nation_flag.name = rel_file_path
        player_obj.save(update_fields=["nation_flag"])
    else:
        print(f"Country {player_obj.nation_abbr} of {player_obj.name} has no flag yet")


def time_from_sec(time):
    min_, sec = divmod(time, 60)
    min_ = int(min_)
    sec = str(int(sec)).zfill(2)
    return f"{min_}:{sec}".rjust(5, "0")
