"""
Complementary functions and constansts for players.views
"""
import datetime
import re
import os
import functools
from itertools import chain, zip_longest
from django.template.loader import render_to_string

from . import models
from pytz import timezone
import json


EMPTY_LIST = []
RANGE_FIELDS = ['weight', 'age']
GAMES_PER_PAGE = 6
TEAM_URL = 'team'
AUTOSEARCH_CSS_PLAYER = 'player'
AUTOSEARCH_CSS_TEAM = 'team'
AUTOSEARCH_CSS_TOTAL = 'total'
ALL_ROWS = 'all'
WHITESPACE = "<br><br>"
MEASUREMENTS_FORMATS = ['USA', 'Europe']
ALERT_ANONYMOUS = 'You are not authenticated. <a href=\"{}\">Register</a> or <a href=\"{}\">Login</a>'
REG_LINK = '//{}/register/'
LOGIN_LINK = '//{}/login/{}'
PAGE_SIZE_OPTIONS = [50, 100, 200]
DEF = 'Defencemen'
FRW = 'Forwards'
TABLE_IDS = ['tab2', 'tab3', 'away_d_men', 'away_fwds', 'home_d_men', 'home_fwds']
FAVORITES_QUOTA = 100
COMPARISON_QUOTA = 5
PAGE_SIZE_1 = 15
PAGE_SIZE_2 = 25
LAST_GAMES_TO_SHOW = 5
SEASON_ENDS = datetime.datetime(2020, 4, 30, 10, 00)
POSITIONS = ['G', 'D', 'C', 'LW', 'RW', 'L', 'R']
STAT_TYPES = ['gls', 'tot', 'avg', 'skt_log', 'gls_log']
SEARCH_RES_DELIMETER = '----------------------------------'
SEARCH_RES_FULL = 'Full results'
DEFAULT_SORTING = {
    'tot': ['-points', 'games', '-goals', 'pk'],
    'avg': ['-points_avg', 'games', '-goals_avg', 'pk'],
    'gls': ['-wins', 'games', 'pk'],
}
MONTHS_MAP = {
    'Jan': 6,
    'Feb': 7,
    'Mar': 8,
    'Apr': 9,
    'May': 10,
    'Jun': 11,
    'Jul': 12,
    'Aug': 1,
    'Sep': 2,
    'Oct': 3,
    'Nov': 4,
    'Dec': 5,
}
HTML_ATTRS = {
    'del_comp_class': "button act-button js-compare-del",
    'del_comp_title': "Remove from comparison",
    'del_comp_html_content': "IN COMPARISON",
    'add_comp_class': "button sm-button js-compare-add",
    'add_comp_title': "Add to comparison",
    'add_comp_html_content': "COMPARE",
    'del_fav_title': "Unfollow player",
    'del_fav_class': "js-fav-del",
    'del_fav_icon_class': "fas fa-star",
    'add_fav_title': "Follow player",
    'add_fav_class': "js-fav-add",
    'add_fav_icon_class': "far fa-star",
}
COLUMNS_SKATERS_GAMELOG = [
    'player.name',
    'team.abbr',
    'format_date',
    'opponent.abbr',
    'goals',
    'assists',
    'points',
    'plusMinus',
    'penaltyMinutes',
    'shots',
    'hits',
    'blocked',
    'faceOffWins',
    'powerPlayPoints',
    'shortHandedPoints',
    'timeOnIce',
    'powerPlayTimeOnIce',
    'shortHandedTimeOnIce',
]
COLUMNS_GOALIES_GAMELOG = [
    'player.name',
    'team.abbr',
    'format_date',
    'opponent.abbr',
    'decision',
    'timeOnIce',
    'goalsAgainst',
    'savePercentage',
    'saves',
    'shots',
    'shutout',
]
COLUMNS = [
    'number',
    'favoriting',
    'name',
    'position_abbr',
    'team',
    'nation_abbr',
    'height',
    'weight',
    'birth_date',
    'age',
    'draft_number',
    'draft_year',
    'games',
]
COLUMNS_AVG = [
    'goals_avg',
    'assists_avg',
    'points_avg',
    'plus_minus_avg',
    'penalty_min_avg',
    'shots_avg',
    'hits_avg',
    'blocks_avg',
    'faceoff_wins_avg',
    'pp_points_avg',
    'sh_points_avg',
]
COLUMNS_TOT = [
    'goals',
    'assists',
    'points',
    'plus_minus',
    'penalty_min',
    'shots',
    'hits',
    'blocks',
    'faceoff_wins',
    'pp_points',
    'sh_points',
]
COLUMNS_TOI = [
    'time_on_ice',
    'time_on_ice_pp',
    'time_on_ice_sh',
]
COLUMNS_GOALIES = [
    'wins',
    'losses',
    'ot_losses',
    'goals_against_av',
    'saves_perc',
    'saves',
    'shotouts',
]

# 'team.name' and 'opponent.name' not being used now
EXTRA_FIELDS = [
    'last_name',
    'height_cm',
    'nation',
    'weight_kg',
    'team.name',
    'opponent.name',
]

EURO_MEASUREMENTS = {
    'height': 'height_cm',
    'weight': 'weight_kg',
}

TOOLTIP_CSS_CLASSES = [
    'cell-with-tooltip',
    'css-tooltip',
    'cell-with-filters-tooltip',
]
MAP_ORDER = {
    0: '',
    1: '-',
}
MAP_GAMELOG_ORDER = {
    0: False,
    1: True,
}
FAV_ALERT_DIV = [
    "<div id=\"pls-fav-alert\" class=\"alert alert-primary js-fav-alert\" role=\"alert\">",
    "<span class=\"js-fav-message\"></span><button type=\"button\" class=\"close\"",
    "data-dismiss=\"alert\" aria-label=\"Close\">",
    "<span aria-hidden=start\"true\">&times;</span></button></div>",
]
SORT_COL_REGEX = r'^\w{3}\[(\d{1,2})\]\=(\d)'
# FILT_COL_REGEX = r'^\w{4}\[(\d{1,2})\]\=([a-zA-Z0-9 ]{1,})'
FILT_COL_REGEX = r'\w{4}\[(\d{1,2})\]\=([a-zA-Z0-9 ]{1,})\ ?\-?\ ?([a-zA-Z0-9 ]{1,})?'
HEIGHT_REGEX = r"(\d)\' (\d{1,2})\""
PLAYER_URL = 'player'
FAVORITE_URL = 'player_favorite'
TEMPLATES = [
    'players/partial_skaters_comparison_season_avg.html',
    'players/partial_skaters_comparison_season_tot.html',
    'players/partial_skaters_comparison_career_avg.html',
    'players/partial_skaters_comparison_career_tot.html',
    'players/partial_goalies_comparison_career_tot.html',
    'players/partial_goalies_comparison_season_tot.html',
    'players/partial_skaters_team_detail.html',
    'players/partial_skaters_team_detail_averages.html',
    'players/game_goalies_table.html',
]
POSITION_FILTERS = [
    'd',
    'f',
    't',
]
SUBTRACT_PERIOD = 1
TIMEZONE = 'US/Pacific'
DATE_TEMPLATE = '%Y-%m-%d'

def checkbox_option(option, checkbox_class, **kwargs):
    classes = TOOLTIP_CSS_CLASSES

    if kwargs['tip']:
        start = f'<label for=\"{option[0]}\" class=\"{checkbox_class} {classes[0]}\">{option[0]} <span class=\"{classes[1]}\">{option[1]}</span></label>'
    else:
        start = f'<label for=\"{option[0]}\" class=\"{checkbox_class} {classes[0]}\">{option[0]} </label>'

    if kwargs['check_this']:
        end = f'<input type=\"checkbox\" class=\"{checkbox_class} checkbox_button\" value=\"{option[0]}\" id=\"{option[0]}\" checked> &nbsp'
    else:
        end = f'<input type=\"checkbox\" class=\"{checkbox_class} checkbox_button\" value=\"{option[0]}\" id=\"{option[0]}\"> &nbsp'

    return start + end


def get_us_pacific_date():
    pacific_datetime = datetime.datetime.now(timezone(TIMEZONE))
    return pacific_datetime.strftime(DATE_TEMPLATE)


def get_adjacent(queryset, today, amount_of_days):
    queryset_length = len(queryset)
    if queryset_length <= amount_of_days:
        return queryset

    todays_index = queryset.index(today)
    go_back_for = amount_of_days // 2
    go_forward_for = amount_of_days - go_back_for
    if todays_index < go_back_for:
        start = 0
        finish = amount_of_days
    else:
        start = todays_index - go_back_for
        finish = todays_index + go_forward_for
        if finish > queryset_length:
            finish = None
            start = queryset_length - amount_of_days

    return queryset[start:finish]


def get_default_date():
    date_now = datetime.date.today()
    return date_now.replace(year=date_now.year - SUBTRACT_PERIOD)


def process_json(request, columns, domain, json, total_rows, start):
    user = request.user
    data = {}
    data["total"] = total_rows
    data["rows"] = []

    for index, player in enumerate(json):
        data["rows"].append([])

        slug = player['fields']['slug']
        nhl_id = str(player['fields']['nhl_id'])
        link = os.path.join('//', domain, PLAYER_URL, slug, nhl_id)

        for column in columns:
            if column == COLUMNS[0]:
                player['fields'][column] = start + (index + 1)

            if column == COLUMNS[1]:
                player['fields'][column] = make_fav_link(request, player, link, column)

            if column == COLUMNS[2]:
                player_name = player['fields'][column]
                player['fields'][column] = make_name_link(player_name, link)

            if column == COLUMNS[4]:
                if player['fields'][column]:
                    value = player['fields'][column][0]
                    tip = player['fields'][column][1]
                else:
                    value = '—'
                    tip = 'No team'
                player['fields'][column] = make_tooltip(value, tip)

            if column == COLUMNS[5]:
                value = player['fields'][column]
                tip = player['fields'][EXTRA_FIELDS[2]]
                player['fields'][column] = make_tooltip(value, tip)

            if user.is_authenticated:
                if measurements_format_is_euro(user):
                    if column in COLUMNS[6]:
                        player['fields'][column] = player['fields'][EXTRA_FIELDS[1]]

                    if column in COLUMNS[7]:
                        player['fields'][column] = player['fields'][EXTRA_FIELDS[3]]

            if column in COLUMNS[10:12]:
                if player['fields'][column] is None:
                    value = '—'
                    tip = 'Undrafted'
                    player['fields'][column] = make_tooltip(value, tip)

            if column == COLUMNS_GOALIES[3]:
                player['fields'][column] = "%.2f" % player['fields'][column]

            if column == COLUMNS_GOALIES[4]:
                player['fields'][column] = "%.3f" % player['fields'][column] 
            if player['fields'][column] is None:
                player['fields'][column] = '—'

            data["rows"][index].append(player['fields'][column])

    return data


def measurements_format_is_euro(user):
    if user.is_authenticated:
        return user.profile.measurements_format == MEASUREMENTS_FORMATS[1]
    return False


def adjust_measurements(player):
    player.weight = player.weight_kg
    player.height = player.height_cm
    return player


def anon_alert(request, redir):
    domain = request.get_host()
    reg_link = REG_LINK.format(domain)
    next_ = f'?next={redir}'
    login_link = LOGIN_LINK.format(domain, next_)
    return ALERT_ANONYMOUS.format(reg_link, login_link)


def parse_url_param(string):
    return int(string.split('=')[1])


def filter_gamelog(games, filtering, columns):
    for sublist in filtering:
        path = columns[int(sublist[0])].split('.')
        query = sublist[1]
        games = [game for game in games if query.lower() in game[path[0]][path[1]].lower()]
    return games


# Sort in reverse and in every iteration rewrite previously sorted array of dicts
def sort_gamelog(sorting, games, columns):
    for sublist in reversed(sorting):
        column = columns[sublist[0]]
        boolean_value = MAP_GAMELOG_ORDER[sublist[1]]
        games = sorted(games, key=lambda game, column=column: get_sorting_value(game, column),
                       reverse=boolean_value)
    return games


# REWRITE FIRST TWO IFS
# ALSO INVESTIGATE WHY TOI SORTING WORKS in players
def get_sorting_value(game, column):
    value = get_cell_value(game, column)
    if 'date' in column:
        return (MONTHS_MAP[value[:3]], int(value[4:]))

    if 'name' in column:
        return value.split()[1]

    # TOI sorting
    if column in COLUMNS_SKATERS_GAMELOG[15:17]:
        min_, sec = value.split(':')
        return int(min_*60) + int(sec)

    return value


def get_cell_value(game, column, *args):
    keys = column.split('.')
    if args:
        return game[keys[0]][args[0]]

    try:
        value = functools.reduce(dict.get, keys, game)
    except TypeError:
        value = None

    if value is None:
        value = '—'
    return value


def get_team_detail_context(team, user):
    stat_type = 'avg'
    pos_filt = 'default'
    sort_order = ['-points', 'games', '-goals']

    context = {
        'goalies': team.goalies.all().order_by('-wins', 'games'),
        'skaters': [
            {
                'type': DEF,
                'list': filter_position(team.skaters.all(), [POSITIONS[1]], sort_order),
                'table_id': TABLE_IDS[0],
            },
            {
                'type': FRW,
                'list': filter_position(team.skaters.all(), POSITIONS[2:], sort_order),
                'table_id': TABLE_IDS[1],
            }
        ],
        'team': team,
        'tbody_skaters': 'players/partial_skaters_team_detail.html',
        'tbody_goalies': 'players/partial_goalies_team_detail.html',
        'stat_type': stat_type,
        'pos_filt': pos_filt,
    }

    if user.is_authenticated:
        if measurements_format_is_euro(user):
            players = chain(context['goalies'], context['skaters'][0]['list'],
                            context['skaters'][1]['list'])

            for player in players:
                player = adjust_measurements(player)

        fav_goalies = team.goalies.all().filter(favoriting__username=user)
        fav_skaters = team.skaters.all().filter(favoriting__username=user)
        fav_players = list(chain(fav_goalies, fav_skaters))
        context['favorites'] = fav_players

    return context


def clear_comparison_list(request, player_type, user):
    data = {}
    field = getattr(user, f'comparable_{player_type}')
    field.clear()
    context = get_comparison_context(user)
    data[f'{player_type}_button'] = f'{player_type.upper()} ({context[f"numb_of_{player_type}"]})'
    template = f'players/partial_{player_type}_comparison_base.html'
    data[f'compare_{player_type}'] = render_to_string(template, context, request=request)
    return data


def get_comparison_context(user):
    stat_type = 'season_avg'
    player_type = 'skaters'
    comp_gls = user.comparable_goalies.select_related('team')
    comp_skt = user.comparable_skaters.select_related('team')
    numb_of_goalies = comp_gls.count()
    numb_of_skaters = comp_skt.count()

    if measurements_format_is_euro(user):
        for player in chain(comp_gls, comp_skt):
            player = adjust_measurements(player)

    context = {
        'comp_gls': comp_gls,
        'comp_skt': comp_skt,
        'favorites_g': comp_gls.filter(favoriting__username=user),
        'favorites_s': comp_skt.filter(favoriting__username=user),
        'stat_type': stat_type,
        'player_type': player_type,
        'numb_of_goalies': numb_of_goalies,
        'numb_of_skaters': numb_of_skaters,
        'empty': (numb_of_goalies + numb_of_skaters == 0),
    }

    return context


def get_fav_alert_div():
    return ''.join(FAV_ALERT_DIV)


def process_json_gamelog(columns, domain, one_page_slice, total_rows):
    data = {}
    data["total"] = total_rows
    data["rows"] = []
    for index, game in enumerate(one_page_slice):
        data["rows"].append([])

        slug = str(game['player']['slug'])
        nhl_id = str(game['player']['nhl_id'])
        link = os.path.join('//', domain, PLAYER_URL, slug, nhl_id)
        player_name = game['player']['name']

        for column in columns:
            cell_value = get_cell_value(game, column)

            if column == COLUMNS_SKATERS_GAMELOG[0]:
                cell_value = make_name_link(player_name, link)

            if column in (COLUMNS_SKATERS_GAMELOG[1], COLUMNS_SKATERS_GAMELOG[3]):
                value = cell_value
                tip = get_cell_value(game, column, 'name')
                cell_value = make_tooltip(value, tip)

            if column == COLUMNS_GOALIES_GAMELOG[7]:
                cell_value = "%.3f" % cell_value

            data["rows"][index].append(cell_value)

    return data


def make_name_link(player_name, link):
    start = "<td class=\"name\"><a class=\"name\""
    end = f"href=\"{link}\">{player_name}</td>"
    return start + end


def make_tooltip(column, tip_field):
    classes = TOOLTIP_CSS_CLASSES
    value = f"<td class=\"{classes[0]}\">{column}"
    tip = f"<span class=\"{classes[1]} {classes[2]}\">{tip_field}</span></td>"
    return value + tip


def make_fav_link(request, player, link, column):
    fav_link = os.path.join(link, FAVORITE_URL)
    # makes a flat array
    player_followers = list(chain.from_iterable(player['fields'][column]))

    if request.user.username in player_followers:
        js_class = "\"js-fav-del\""
        title = "\"Unfollow player\""
        font_class = "\"fas fa-star\""
    else:
        js_class = "\"js-fav-add\""
        title = "\"Follow player\""
        font_class = "\"far fa-star\""

    start = "<div id=\"favorite_section\">"
    middle = f"<a class={js_class} href=\"{fav_link}\" title={title}>"
    end = f"<i class={font_class}></i></a></div>"

    return start + middle + end


def sort_table(request, stat_type, sorting, players_query, columns):
    user = request.user
    if sorting:
        sorting_args = []
        for sub_list in sorting:
            if sub_list[0] == 2:
                # sort names as lastnames
                sorting_args.append(f'{MAP_ORDER[sub_list[1]]}{EXTRA_FIELDS[0]}')
            elif sub_list[0] == 4:
                # sort by team.abbr
                sorting_args.append(f'{MAP_ORDER[sub_list[1]]}{columns[sub_list[0]]}__abbr')
            elif sub_list[0] == 6:
                # sort height as height in cm
                sorting_args.append(f'{MAP_ORDER[sub_list[1]]}{EXTRA_FIELDS[1]}')
            elif sub_list[0] == 7:
                # sort weight by kilos if user chose a euro format
                if user.is_authenticated:
                    if measurements_format_is_euro(user):
                        sorting_args.append(f'{MAP_ORDER[sub_list[1]]}{EXTRA_FIELDS[3]}')
                    else:
                        sorting_args.append(f'{MAP_ORDER[sub_list[1]]}{columns[sub_list[0]]}')
            else:
                sorting_args.append(f'{MAP_ORDER[sub_list[1]]}{columns[sub_list[0]]}')
        sorting_args.append('pk')
    else:
        sorting_args = DEFAULT_SORTING[stat_type]
    return players_query.order_by(*sorting_args)


def apply_filters(request, players_query, filtering, columns):
    kwargs = {}
    user = request.user
    adjust_range = False
    for sub_list in filtering:
        field = columns[int(sub_list[0])]
        if len(sub_list) > 2:
            if user.is_authenticated:
                if measurements_format_is_euro(user):  
                    if field == columns[6] or field == columns[7]:
                        kwargs[f'{EURO_MEASUREMENTS[field]}__range'] = (sub_list[1], sub_list[2])
                    else:
                        kwargs[f'{field}__range'] = (sub_list[1], sub_list[2])

                else:
                    kwargs[f'{field}__range'] = (sub_list[1], sub_list[2])
        else:
            # filter team name
            if field == columns[4]:
                kwargs[f'{field}__abbr__icontains'] = sub_list[1]
            # filter full nation name
            elif field == columns[5]:
                kwargs[f'{EXTRA_FIELDS[2]}__icontains'] = sub_list[1]
            else:
                kwargs[f'{field}__icontains'] = sub_list[1]

            adjust_range = True

    return (players_query.filter(**kwargs), adjust_range)

def filter_checkbox_opts(players_query, field_names):
    sorted_opts = []
    for field in field_names:
        sorted_opts.append(sort_list(get_uniques(players_query, field)))

    if len(sorted_opts) > 1:
        sorted_opts = zip(sorted_opts[0], sorted_opts[1])
    else:
        sorted_opts = zip_longest(sorted_opts[0], EMPTY_LIST)

    return [el if el is not None else '—' for el in sorted_opts]


def get_uniques(queryset, field):
    return list(queryset.values_list(field, flat=True).distinct())


def sort_list(array):
    return sorted(array, key=lambda x: (x is None, x))


def sort_height_list(height_list):
    dict_height = {}
    for value in height_list:
        match = re.search(HEIGHT_REGEX, value)

        # to sort None and empty string values with integers
        if match:
            dict_height[value] = (bool(value), int(match[1]), int(match[2]))
        else:
            dict_height[value] = (bool(value), value, value)

    sorted_by_value = sorted(dict_height.items(), key=lambda item: item[1])

    return [element[0] for element in sorted_by_value]


def sorting_columns(sort_col):
    columns = sort_col.split('&')

    array = []
    for index, column in enumerate(columns):
        matches = re.search(SORT_COL_REGEX, column)
        if matches:
            array.append([])
            array[index].append(int(matches[1]))
            array[index].append(int(matches[2]))

    return array


def filter_columns(filt_col):
    columns = filt_col.split('&')

    array = []
    for index, column in enumerate(columns):
        matches = re.search(FILT_COL_REGEX, column)

        if matches:
            array.append([])
            array[index].append(matches[1])
            # Removes extra whitespaces between first and last name
            array[index].append(' '.join(matches[2].split()))
            if matches[3]:
                array[index].append(' '.join(matches[3].split()))

    return array


def rookie_filter(rookie_filt):
    if rookie_filt.split('=')[1]:
        return True
    return False


def checkbox_filter(checkbox_filt, column):
    if checkbox_filt.split('=')[1]:
        team_str = checkbox_filt.split('=')[1]
        team_str = json.loads(team_str)

        try:
            return team_str[column]
        except (KeyError, TypeError):
            return False

    return False


def add_comp_info(request, player):
    """
    Sets HTML attributes for initial load on a player_detail page

    To avoid an extra if condition in a player_detail template

    Args:
      request: HttpRequest object
      player: object of Skater's or Goalie's models

    Returns:
        A nested dictionary with HTML attributes for a 'player_compare' link
    """
    context = {}
    context['comp'] = {}
    if is_compare(request, player):
        context['comp']['class'] = HTML_ATTRS['del_comp_class']
        context['comp']['title'] = HTML_ATTRS['del_comp_title']
        context['comp']['html_content'] = HTML_ATTRS['del_comp_html_content']
    else:
        context['comp']['class'] = HTML_ATTRS['add_comp_class']
        context['comp']['title'] = HTML_ATTRS['add_comp_title']
        context['comp']['html_content'] = HTML_ATTRS['add_comp_html_content']

    return context


def add_fav_info(request, player):
    """
    Sets HTML attributes for initial load on a player_detail page

    To avoid an extra if condition in a player_detail template

    Args:
      request: HttpRequest object
      player: object of Skater's or Goalie's models

    Returns:
        A nested dictionary with HTML attributes for a 'player_favorite' link
    """
    context = {}
    context['fav'] = {}
    if is_favorite(request, player):
        context['fav']['class'] = HTML_ATTRS['del_fav_class']
        context['fav']['title'] = HTML_ATTRS['del_fav_title']
        context['fav']['icon_class'] = HTML_ATTRS['del_fav_icon_class']
    else:
        context['fav']['class'] = HTML_ATTRS['add_fav_class']
        context['fav']['title'] = HTML_ATTRS['add_fav_title']
        context['fav']['icon_class'] = HTML_ATTRS['add_fav_icon_class']

    return context


def favorite_players_gamelog(fav_players):
    """
    Gets an array with all games of players from a QuerySet object

    Args:
      fav_players: QuerySet object with favorited objects of Skater
            or Goalie models

    Returns:
        Sorted by date array of dictionaries, when one dictionary represents
        a data for one NHL game of a player
    """
    games_list = []

    for player in fav_players.iterator():
        for _, game in player.gamelog_stats.items():
            games_list.append(game)

    return sorted(games_list, reverse=True,
                  key=lambda x: (MONTHS_MAP[x['format_date'][:3]], int(x['format_date'][4:])))


def get_checked_dict(player, positions_extra):
    """
    Gets a dictionary with positions as keys to iterate in player_detail.html

    Dictionary is needed to implement a checkbox when user changes positions
    for a player. Boolean attribute `checked` mapped to the positions accordingly
    to make the HTML `input type="checkbox"` element pre-selected (checked).
    Positon is assigned to None if the element should not be checked on the
    HTML page

    Args:
        player: object of Skater's model
        positions_extra: object of Position model for given player and
            authenticated user or None if object does not exists

    Returns:
        A dictionary with all Skaters positions as keys mapped to the
        correponding values.
    """
    # List of positions to check
    if positions_extra:
        pos = positions_extra.data
    else:
        pos = [player.position_abbr]

    # Creating a dict with checked/unchecked positions
    checked_dict = {
        key: 'checked' if key in pos else None for key in POSITIONS[1:5]
    }

    return checked_dict


def unpack_list_positions(player, positions_extra):
    """
    Makes a string to be be shown as a value for a `Positions` in the HTML

    Args:
      player: object of Skater's model
      positions_extra: object of Position model for given player and
          authenticated user or None if object does not exists

    Returns:
        String with joined list values if positions_extra has value. If not -
        just returns a string with default position for a player.
    """
    if positions_extra:
        return (', ').join(positions_extra.data)

    return player.position_abbr


def get_object(request, player, model_name):
    """
    Retrieves an object from Position or Note models

    Returns an object for given player and authenticated user or None
    if object does not exists. Needed to show value of the note or positions
    field on the HTML page. Used in views.player_detail

    Args:
      request: HttpRequest object
      player: object of Skater or Goalie models
      model_name: Name of the model without quotes - Note or Position
    """
    user = request.user
    if user.is_authenticated:
        try:
            return model_name.objects.get(author_id=user.id, object_id=player.pk)
        except model_name.DoesNotExist:
            pass

    return None


def season_in_prog():
    """
    Returns a boolean value indicating that season is in progress or not

    Needed for scripts that will not load any new data into the DB if
    the function returns true eg. season is over.
    SEASON_ENDS is a constant with a datetime object.
    """
    return SEASON_ENDS > datetime.datetime.now()


def get_player(nhl_id, slug):
    """
    Fetches object of Skater or Goalie models

    If object is not found in either of models it returns `None`

    Args:
        nhl_id: integer representing a player's id from nhl.com API
        slug: a string representing a slug of an object
    """
    try:
        return models.Skater.objects.select_related('team').get(nhl_id=nhl_id, slug=slug)
    except models.Skater.DoesNotExist:
        try:
            return models.Goalie.objects.select_related('team').get(nhl_id=nhl_id, slug=slug)
        except models.Goalie.DoesNotExist:
            return None


def is_favorite(request, player):
    """
    Determines if player is in favorites for authenticated user

    Args:
      request: HttpRequest object
      player: object of Skater's or Goalie's models

    Returns:
        a boolean value indicating that object is added to favorites by
        authenticated user or not
    """
    if player.favoriting.filter(id=request.user.id).exists():
        return True
    return False


def is_compare(request, player):
    """
    Determines if player is in comparison for authenticated user

    Args:
      request: HttpRequest object
      player: object of Skater's or Goalie's models

    Returns:
        a boolean value indicating that object is in progress or not

    """
    if player.comparing.filter(id=request.user.id).exists():
        return True
    return False


def get_user_favorites(request):
    """
    Fetches all players favorited by the authenticated user

    Returns a dictionary with two keys. Key with value of QuerySet object for
    goalies favorited by the authenticated user and key with value of QuerySet
    object for skaters favorited by the authenticated user

    Args:
      request: HttpRequest object
    """
    user = request.user
    context = {}
    if user.is_authenticated:
        context['favorites_g'] = user.favorite_goalies.all()
        context['favorites_s'] = user.favorite_skaters.all()
    return context


def get_user_compares(request):
    """
    Fetches all players compared by the authenticated user

    Returns a dictionary with two keys. Key with value of QuerySet object for
    goalies compared by the authenticated user and key with value of QuerySet
    object for skaters compared by the authenticated user.

    Args:
      request: HttpRequest object
    """
    user = request.user
    context = {}
    if user.is_authenticated:
        context['compare_g'] = user.comparable_goalies.all()
        context['compare_s'] = user.comparable_skaters.all()
    return context


def get_gamelog(player, *slicer):
    """
    Returns a number of player's last games from a JSONField accordingly
        to the *slicer argument

    Returns an empty list if JSONField is empty

    Args:
      player: object of Skater's or Goalie's models
      *slicer: a tuple with an optional argument as a slicer
          constructor to slice the desired number of elements   
    """
    log = player.gamelog_stats
    if not log:
        return []

    sorted_log = [log[key] for key in sorted(list(log), reverse=True)]
    if not slicer:
        return sorted_log

    return sorted_log[slicer[0]]


def filter_position(queryset, positions, order):
    """
    Filter objects of Skater model by position.

    Returns a QuerySet object. Sorted accordingly to the order argument.

    Args:
      queryset: QuerySet object to lookup
      positions: a list of positions to use in a field lookup
      order: a list of Django model fields to sort by
    """
    query_by_position = queryset.filter(position_abbr__in=positions)
    return query_by_position.order_by(*order)


def pop_key(dictionary, key):
    """
    Removes a given key from a dictionary used as a parameter in JsonResponse

    Used as indicator in AJAX calls. Key will be removed if it was added
    at the previous AJAX call.

    Example:

    player.favorite.remove(user)
    data['message'] = f'{player.name} successfully removed from the favorites'
    utils.pop_key(data, 'fav_quota_reached')

    Args:
      dictionary: a dictionary representing a data parameter from a JsonResponse
      key: a string with a key to be removed
    """
    if key in dictionary:
        dictionary.pop(key)
