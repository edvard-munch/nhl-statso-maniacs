import json
import os
from itertools import chain

from django.core import serializers
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from . import utils
from .forms import NoteForm, PositionsForm
from .models import Game, Gameday, Goalie, Note, Position, Skater, Team


def home(request):
    return render(request, 'players/home.html', {'title': 'Home'})


def about(request):
    return render(request, 'players/about.html', {'title': 'About'})


def games(request, date=utils.get_us_pacific_date()):
    context = {}
    gamedays = list(Gameday.objects.all().order_by('day'))
    try:
        today = Gameday.objects.get(day=date)
    except Gameday.DoesNotExist:
        today = Gameday.objects.last()
    days_per_page = utils.get_adjacent(gamedays, today, utils.GAMES_PER_PAGE)

    context = {
        'today': today,
        'days_per_page': days_per_page,
    }

    return render(request, 'players/games.html', context)


def game_detail(request, slug, nhl_id):
    game = Game.objects.get(nhl_id=nhl_id, slug=slug)
    user = request.user
    sort_order = ['last_name']

    context = {
        'game': game,
        'skaters': [
            {
                'header': game.side_set.get(side='away').team,
                'list': game.away_forwards.all(). order_by(*sort_order),
                'type': utils.FRW,
                'table_id': utils.TABLE_IDS[3],
            },
            {
                'list': game.away_defencemen.all(). order_by(*sort_order),
                'type': utils.DEF,
                'table_id': utils.TABLE_IDS[2],
                'game_goalies_table': {
                    'template': utils.TEMPLATES[8],
                    'list': game.away_goalies.all(),
                },
                'whitespace': utils.WHITESPACE,
            },
            {
                'header': game.side_set.get(side='home').team,
                'list': game.home_forwards.all(). order_by(*sort_order),
                'type': utils.FRW,
                'table_id': utils.TABLE_IDS[5],
            },
            {
                'list': game.home_defencemen.all(). order_by(*sort_order),
                'type': utils.DEF,
                'table_id': utils.TABLE_IDS[4],
                'game_goalies_table': {
                    'template': utils.TEMPLATES[8],
                    'list': game.home_goalies.all(),
                },
                'whitespace': utils.WHITESPACE,
            },
        ],
    }

    if user.is_authenticated:
        fav_away_goalies = game.away_goalies.all().filter(favoriting__username=user)
        fav_home_goalies = game.home_goalies.all().filter(favoriting__username=user)
        fav_away_defencemen = game.away_defencemen.all().filter(favoriting__username=user)
        fav_home_defencemen = game.home_defencemen.all().filter(favoriting__username=user)
        fav_away_forwards = game.away_forwards.all().filter(favoriting__username=user)
        fav_home_forwards = game.home_forwards.all().filter(favoriting__username=user)
        fav_players = list(chain(fav_away_goalies, fav_home_goalies,fav_away_defencemen,
                                 fav_home_defencemen, fav_away_forwards, fav_home_forwards))

        context['favorites'] = fav_players

    return render(request, 'players/game_detail.html', context)


def auth_callback(request):
    context = {
        'title': 'auth_callback',
        'code': request.GET.get("code"),
    }

    return render(request, 'auth_callback.html', context)


def players(request):
    context = {
        'title': 'Players',
        'options': utils.PAGE_SIZE_OPTIONS,
        'table_page_size': utils.PAGE_SIZE_2,
    }

    return render(request, 'players/players.html', context)


def favorites(request):
    context = {}
    user = request.user
    if user.is_authenticated:
        fav_goalies = user.favorite_goalies.select_related('team')
        fav_skaters = user.favorite_skaters.select_related('team')
        skaters_games = utils.favorite_players_gamelog(fav_skaters)
        goalies_games = utils.favorite_players_gamelog(fav_goalies)
        numb_of_skaters = fav_skaters.count()
        numb_of_goalies = fav_goalies.count()

        if utils.measurements_format_is_euro(user):
            for player in chain(fav_goalies, fav_skaters):
                player = utils.adjust_measurements(player)

        options = utils.PAGE_SIZE_OPTIONS
        skaters_options = [option for option in options if option < numb_of_skaters]
        goalies_options = [option for option in options if option < numb_of_goalies]
        skaters_games_options = [option for option in options if option < len(skaters_games[:200])]
        goalies_games_options = [option for option in options if option < len(goalies_games[:200])]

        context = {
            'favorites_g': fav_goalies,
            'favorites_s': fav_skaters,
            'numb_of_goalies': numb_of_goalies,
            'numb_of_skaters': numb_of_skaters,
            'table_page_size': utils.PAGE_SIZE_2,
            'skaters_options': skaters_options,
            'goalies_options': goalies_options,
            'skaters_games_options': skaters_games_options,
            'goalies_games_options': goalies_games_options,
        }

    return render(request, 'players/favorites.html', context)


def ajax_fav_players_gamelog(request, stat_type, page, size, sort_col, filt_col):
    page = utils.parse_url_param(page)
    user = request.user
    if user.is_authenticated:
        if stat_type == utils.STAT_TYPES[3]:
            fav_players = user.favorite_skaters.select_related('team')
            columns = utils.COLUMNS_SKATERS_GAMELOG
        elif stat_type == utils.STAT_TYPES[4]:
            fav_players = user.favorite_goalies.select_related('team')
            columns = utils.COLUMNS_GOALIES_GAMELOG

        all_games = utils.favorite_players_gamelog(fav_players)

        if utils.ALL_ROWS in size:
            size = len(all_games)
        else:
            size = utils.parse_url_param(size)

        start = int(size)*(int(page) - 1)
        end = start + int(size)

        filtering = utils.filter_columns(filt_col)
        if filtering:
            all_games = utils.filter_gamelog(all_games, filtering, columns)

        sorting = utils.sorting_columns(sort_col)
        if sorting:
            one_page_slice = utils.sort_gamelog(sorting, all_games, columns)[start:end]
        else:
            one_page_slice = all_games[start:end]

        total_rows = len(all_games)
        domain = request.get_host()

        data = utils.process_json_gamelog(columns, domain, one_page_slice, total_rows)
        return JsonResponse(data, safe=False)


def ajax_players(request, stat_type, page, size, sort_col, filt_col, rookie_filt, checkbox_filt, fav_filt=None):
    page = utils.parse_url_param(page)
    user = request.user
    favorites = False
    if user.is_authenticated:
        if fav_filt:
            favorites = True
    if stat_type == utils.STAT_TYPES[0]:
        columns = utils.COLUMNS + utils.COLUMNS_GOALIES
        if favorites:
            players = user.favorite_goalies.select_related('team')
        else:
            players = Goalie.objects.select_related('team')
    else:
        if stat_type == utils.STAT_TYPES[1]:
            columns = utils.COLUMNS + utils.COLUMNS_TOT + utils.COLUMNS_TOI
        elif stat_type == utils.STAT_TYPES[2]:
            columns = utils.COLUMNS + utils.COLUMNS_AVG + utils.COLUMNS_TOI
        if favorites:
            players = user.favorite_skaters.select_related('team')
        else:
            players = Skater.objects.select_related('team')

    init_age_range = utils.get_range(players, 'age')

    if utils.measurements_format_is_euro(user):
        init_weight_range = utils.get_range(players, 'weight_kg')
    else:
        init_weight_range = utils.get_range(players, 'weight')

    init_height_range = utils.get_range(players, 'height_cm')

    if utils.ALL_ROWS in size:
        size = players.count()
    else:
        size = utils.parse_url_param(size)

    start = size*(page - 1)
    end = start + size

    # ALL CHECKBOX OPTIONS BEFORE STANDARDFILTERING
    positions_before_position_filt = utils.filter_checkbox_opts(players, ('position_abbr', 'position_name'))
    teams_before_team_filt = utils.filter_checkbox_opts(players, ('team__abbr', 'team__name'))
    nations_before_nation_filt = utils.filter_checkbox_opts(players, ('nation',))

    filtering = utils.filter_columns(filt_col)
    if filtering:
        players = utils.apply_filters(request, players, filtering, columns)[0]
        adjust_range = utils.apply_filters(request, players, filtering, columns)[1]
        if adjust_range:
            pass
            # adjust range call

    # if utils.rookie_filter(rookie_filt):
    #     players = players.filter(rookie=True)

    # ALL CHECKBOX OPTIONS JUST AFTER STANDARD FILTERING
    all_positions = utils.filter_checkbox_opts(players, ('position_abbr', 'position_name'))
    all_teams = utils.filter_checkbox_opts(players, ('team__abbr', 'team__name'))
    all_nations = utils.filter_checkbox_opts(players, ('nation',))

    filtered_teams = utils.checkbox_filter(checkbox_filt, 'teams')
    if filtered_teams:
        players = players.filter(team__abbr__in=filtered_teams)  # .prefetch_related()

    filtered_positions = utils.checkbox_filter(checkbox_filt, 'positions')
    if filtered_positions:
        players = players.filter(position_abbr__in=filtered_positions)  # .prefetch_related()

    filtered_nations = utils.checkbox_filter(checkbox_filt, 'nations')
    if filtered_nations:
        players = players.filter(nation__in=filtered_nations)  # .prefetch_related()

    sorting = utils.sorting_columns(sort_col)
    one_page_slice = utils.sort_table(request, stat_type, sorting, players, columns)[start:end]

    players_json = json.loads(serializers.serialize('json', one_page_slice,
                                                    use_natural_foreign_keys=True))
    domain = request.get_host()
    total_rows = players.count()
    data = utils.process_json(request, columns, domain, players_json, total_rows, start)

    data['initial_age_range'] = init_age_range
    data['initial_weight_range'] = init_weight_range
    data['initial_height_range'] = init_height_range

    # data['pager'] = total_rows < utils.PAGE_SIZE_2

    # IF FILTERING CONTAINS RANGES - GET what range is used (check in ARRAY with all range fields)
    # and pass it to range_applied

    data['fav_alert_div'] = utils.get_fav_alert_div()

    # CHECK AND OPTIMIZE ALL OF THE IF BRANCHES HERE

    # GET HTML for checkbox OPTIONS after standard filtering have been applied or not
    data['all_teams'] = utils.checkbox(all_teams, 'team_checkboxradio_skt', tip=True)
    data['all_nations'] = utils.checkbox(all_nations, 'nation_checkboxradio_skt', tip=False)
    data['all_positions'] = utils.checkbox(all_positions, 'position_checkboxradio_skt', tip=True)

        
    # All below is for getting HTML for checkbox OPTIONS if  STANDARD of CHECKBOX filtering have been applied 

    # remove or make not active teams that doesn't have players for current filter set besides checkbox filters
    if filtering:
        data['all_teams'] = utils.checkbox(all_teams, 'team_checkboxradio_skt', tip=True)
        data['all_nations'] = utils.checkbox(all_nations, 'nation_checkboxradio_skt', tip=False)
        data['all_positions'] = utils.checkbox(all_positions, 'position_checkboxradio_skt', tip=True)

# IF CHECKED
    if(utils.checkbox_filter(checkbox_filt, 'teams')):
        data['all_teams'] = utils.checkbox(all_teams, 'team_checkboxradio_skt', checked=utils.checkbox_filter(checkbox_filt, 'teams'), tip=True)
        # remove or make not active teams that doesn't have players for current filter set besides checkbox filters
        if filtering:
        # make a special players list without filtering by team and make a teams list from it
        # it works fine before check any team, then it leaves only currrently checked team
        # because there really a filtering and when you also check a team, it's obviously leaves only this team as an option
            data['all_teams'] = utils.checkbox(teams_before_team_filt, 'team_checkboxradio_skt', checked=utils.checkbox_filter(checkbox_filt, 'teams'), tip=True)

    if(utils.checkbox_filter(checkbox_filt, 'positions')):
        data['all_positions'] = utils.checkbox(all_positions, 'position_checkboxradio_skt', checked=utils.checkbox_filter(checkbox_filt, 'positions'), tip=True)
        if filtering:
            data['all_positions'] = utils.checkbox(positions_before_position_filt, 'position_checkboxradio_skt', checked=utils.checkbox_filter(checkbox_filt, 'positions'), tip=True)

    if(utils.checkbox_filter(checkbox_filt, 'nations')):
        data['all_nations'] = utils.checkbox(all_nations, 'nation_checkboxradio_skt', checked=utils.checkbox_filter(checkbox_filt, 'nations'), tip=False)
        if filtering:
            data['all_nations'] = utils.checkbox(nations_before_nation_filt, 'nation_checkboxradio_skt', checked=utils.checkbox_filter(checkbox_filt, 'nations'), tip=False)

    uniques_height_cm = utils.get_uniques(players, 'height_cm')
    uniques_height_cm = utils.sort_list(uniques_height_cm)
    uniques_height = utils.get_uniques(players, 'height')
    uniques_height = utils.sort_height_list(uniques_height)
    height_map_dict = dict(zip(uniques_height_cm, uniques_height))

    if utils.measurements_format_is_euro(user):
        data['weight_range'] = utils.get_range(players, 'weight_kg')
        data['height_values'] = uniques_height_cm
    else:
        data['weight_range'] = utils.get_range(players, 'weight')
        data['height_values'] = height_map_dict

    data['height_range'] = utils.get_range(players, 'height_cm')
    data['age_range'] = utils.get_range(players, 'age')

    return JsonResponse(data, safe=False)


def search(request):
    if 'q' in request.GET and request.GET['q']:
        query = request.GET['q'].strip()

        result_skaters = Skater.objects.filter(name__icontains=query)
        result_goalies = Goalie.objects.filter(name__icontains=query)
        result_teams = Team.objects.filter(name__icontains=query)
        result_players = list(chain(result_skaters, result_goalies))

        context = {
            'players': result_players,
            'query': query,
            'teams': result_teams,
        }

        user = request.user
        if user.is_authenticated:
            context_extra = {
                'favorites_g': result_goalies.filter(favoriting__username=user),
                'favorites_s': result_skaters.filter(favoriting__username=user),
                'compare_g': result_goalies.filter(comparing__username=user),
                'compare_s': result_skaters.filter(comparing__username=user),
            }

            context = {**context, **context_extra}
        return render(request, 'players/search_results.html', context)

    return HttpResponse('Please submit a search term.')


def autocomplete(request):
    query = request.GET.get('term', '').strip()

    search_s = Skater.objects.filter(name__icontains=query)
    search_g = Goalie.objects.filter(name__icontains=query)
    search_t = Team.objects.filter(name__icontains=query)
    search_qs = list(chain(search_s, search_g))

    if search_qs and search_t:
        search_qs.append(utils.SEARCH_RES_DELIMETER)

    if search_t:
        search_qs += list(search_t)

    if search_qs or search_t:
        search_qs.append(utils.SEARCH_RES_DELIMETER)
        search_qs.append(utils.SEARCH_RES_FULL)

    data = {}
    domain = request.get_host()

    for index, res in enumerate(search_qs):
        data[index] = {}

        if res == utils.SEARCH_RES_FULL:
            link = os.path.join('//', domain, f'search?q={query}')
            href = f'href=\"{link}\">{utils.SEARCH_RES_FULL}'
            data[index]['label'] = f"<a class=\"{utils.AUTOSEARCH_CSS_TOTAL}\"{href}</a>"
            data[index]['value'] = utils.SEARCH_RES_FULL
        elif res == utils.SEARCH_RES_DELIMETER:
            data[index]['label'] = res

        else:
            if isinstance(res, Team):
                url_mid_part = utils.TEAM_URL
                css_class = utils.AUTOSEARCH_CSS_TEAM
            else:
                url_mid_part = utils.PLAYER_URL
                css_class = utils.AUTOSEARCH_CSS_PLAYER

            link = os.path.join('//', domain, url_mid_part, res.slug, str(res.nhl_id))
            href = f'href=\"{link}\">{res.name}'
            data[index]['label'] = f"<a class=\"{css_class}\"{href}</a>"
            data[index]['value'] = res.name

    return JsonResponse(data)


def player_detail(request, slug, nhl_id):
    player = utils.get_player(nhl_id, slug)
    user = request.user
    if user.is_authenticated:
        if utils.measurements_format_is_euro(user):
            player = utils.adjust_measurements(player)

    skater = player.position_abbr in utils.POSITIONS[1:]
    slicer = slice(utils.LAST_GAMES_TO_SHOW)

    context = {
        'player': player,
        # for a goalie
        'sbs_stats': player.sbs_stats,
        'total': player.career_stats,
        # for a skater
        'stats': [
            {
                'stats': player.sbs_stats,
                'title': 'Career',
                'total': player.career_stats,
            },
        ],

        'last_gms': utils.get_gamelog(player, slicer),
        'proj_stats': utils.season_in_prog() and player.proj_stats,
        'note': utils.get_object(request, player, Note),
        'skater': skater,
        'note_max_length': Note._meta.get_field('text').max_length,
    }

    if skater:
        avg_dict = {
            'stats': player.sbs_stats_avg,
            'title': 'Career averages',
            'total': player.career_stats_avg,
        }
        context['stats'].append(avg_dict)

        positions_extra = utils.get_object(request, player, Position)
        context['checked_dict'] = utils.get_checked_dict(player, positions_extra)
        context['positions'] = utils.unpack_list_positions(player, positions_extra)

    context = {**context, **utils.add_comp_info(request, player),
               **utils.add_fav_info(request, player)}

    return render(request, 'players/player_detail.html', context)


def player_gamelog(request, slug, nhl_id):
    player = utils.get_player(nhl_id, slug)
    gamelog = utils.get_gamelog(player)
    options = utils.PAGE_SIZE_OPTIONS
    gamelog_size = len(gamelog)
    gamelog_options = [option for option in options if option < gamelog_size]

    context = {
        'player': player,
        'gamelog': gamelog,
        'gamelog_options': gamelog_options,
        'pager': gamelog_size > utils.PAGE_SIZE_2,
      }

    return render(request, 'players/player_gamelog.html', context)


def teams(request):
    context = {
        'teams': Team.objects.all().order_by('name'),
    }

    return render(request, 'players/teams.html', context)


def team_detail(request, slug, team_id):
    team = get_object_or_404(Team, nhl_id=team_id, slug=slug)
    user = request.user
    context = utils.get_team_detail_context(team, user)
    return render(request, 'players/team_detail.html', context)


def ajax_stats_switcher(request, slug, team_id, stat_type, pos_filt):
    team = get_object_or_404(Team, nhl_id=team_id, slug=slug)
    user = request.user
    context = utils.get_team_detail_context(team, user)
    if stat_type == utils.STAT_TYPES[1]:
        template = utils.TEMPLATES[6]
    elif stat_type == utils.STAT_TYPES[2]:
        template = utils.TEMPLATES[7]

    sort_order = ['-points', 'games', '-goals']
    d_men = utils.filter_position(team.skaters.all(), [utils.POSITIONS[1]], sort_order)
    forwards = utils.filter_position(team.skaters.all(), utils.POSITIONS[2:], sort_order)
    skaters = utils.filter_position(team.skaters.all(), utils.POSITIONS[1:], sort_order)

    if pos_filt == utils.POSITION_FILTERS[0]:
        filtered_skaters = {'list': d_men}
    elif pos_filt == utils.POSITION_FILTERS[1]:
        filtered_skaters = {'list': forwards}
    elif pos_filt == utils.POSITION_FILTERS[2]:
        filtered_skaters = {'list': skaters}

    if utils.measurements_format_is_euro(user):
        for player in filtered_skaters['list']:
            player = utils.adjust_measurements(player)

    context['object'] = filtered_skaters
    data = {}
    data['stats'] = render_to_string(template, context=context, request=request)

    return JsonResponse(data)


def ajax_comparison_stat_switcher(request, player_type, stat_type):
    user = request.user
    if user.is_authenticated:
        comp_gls = user.comparable_goalies.select_related('team')
        comp_skt = user.comparable_skaters.select_related('team')

        context = {
            'comp_gls': comp_gls,
            'comp_skt': comp_skt,
            'favorites_g': comp_gls.filter(favoriting__username=user),
            'favorites_s': comp_skt.filter(favoriting__username=user),
        }

        if player_type == 'skaters':
            if stat_type == 'season_avg':
                template = utils.TEMPLATES[0]
            elif stat_type == 'season_tot':
                template = utils.TEMPLATES[1]
            elif stat_type == 'career_avg':
                template = utils.TEMPLATES[2]
            elif stat_type == 'career_tot':
                template = utils.TEMPLATES[3]
        elif player_type == 'goalies':
            if stat_type == 'career_tot':
                template = utils.TEMPLATES[4]
            if stat_type == 'season_tot':
                template = utils.TEMPLATES[5]

        data = {}
        data['stats'] = render_to_string(template, context=context, request=request)

        return JsonResponse(data)


def comparison(request):
    context = {}
    user = request.user
    if user.is_authenticated:
        context = utils.get_comparison_context(user)

    return render(request, 'players/comparison.html', context)


def player_compare(request, slug, nhl_id):
    data = {}
    user = request.user
    if user.is_authenticated:
        data['authenticated'] = True
        player = utils.get_player(nhl_id, slug)
        if player.position_abbr == utils.POSITIONS[0]:
            quota = user.comparable_goalies.count()
        else:
            quota = user.comparable_skaters.count()

        if player.comparing.filter(id=user.id).exists():
            player.comparing.remove(user)
            data['message'] = f'{player.name} successfully removed from the comparison'
            utils.pop_key(data, 'comp_quota_reached')
            context = utils.get_comparison_context(user)

            data['goalies_button'] = f'GOALIES ({context["numb_of_goalies"]})'
            data['skaters_button'] = f'SKATERS ({context["numb_of_skaters"]})'

            data['compare_skaters'] = render_to_string('players/partial_skaters_comparison_base.html',
                                                       context, request=request)
            data['compare_goalies'] = render_to_string('players/partial_goalies_comparison_base.html',
                                                       context, request=request)
        else:
            if quota < utils.COMPARISON_QUOTA:
                player.comparing.add(user)
                data['message'] = f'{player.name} successfully added to the comparison'
                utils.pop_key(data, 'comp_quota_reached')

            else:
                data['message'] = f'Comparison quota reached ({utils.COMPARISON_QUOTA} players)'
                data['comp_quota_reached'] = 1
    else:
        data['authenticated'] = False
        redir = request.META.get('HTTP_REFERER')
        data['message'] = utils.anon_alert(request, redir)

    return JsonResponse(data)


def reset_comparison(request, player_type):
    user = request.user
    if user.is_authenticated:
        data = utils.clear_comparison_list(request, player_type, user)

    return JsonResponse(data)


def player_favorite(request, slug, nhl_id):
    data = {}
    user = request.user
    if user.is_authenticated:
        data['authenticated'] = True
        quota = user.favorite_skaters.count() + user.favorite_goalies.count()
        player = utils.get_player(nhl_id, slug)
        if player.favoriting.filter(id=user.id).exists():
            player.favoriting.remove(user)
            data['message'] = f'{player.name} successfully removed from the favorites'
            utils.pop_key(data, 'fav_quota_reached')
            data['skaters_count'] = user.favorite_skaters.count()
            data['goalies_count'] = user.favorite_goalies.count()
        else:
            if quota < utils.FAVORITES_QUOTA:
                player.favoriting.add(user)
                data['message'] = f'{player.name} successfully added to the favorites'
                utils.pop_key(data, 'fav_quota_reached')
            else:
                data['message'] = f'Favorites quota reached ({utils.FAVORITES_QUOTA} players)'
                data['fav_quota_reached'] = 1
    else:
        data['authenticated'] = False
        redir = request.META.get('HTTP_REFERER')
        data['message'] = utils.anon_alert(request, redir)

    return JsonResponse(data)


def player_note(request, slug, nhl_id):
    data = {}
    user = request.user
    if user.is_authenticated:
        data['authenticated'] = True
        player = utils.get_player(nhl_id, slug)
        if request.method == 'POST':
            form = NoteForm(request.POST)
            if form.is_valid():
                text = form.cleaned_data['text']
                if text:
                    defaults = {
                        'text': text,
                        'player_name': player.name,
                    }

                    Note.objects.update_or_create(object_id=player.pk,
                                                  author_id=request.user.id,
                                                  defaults=defaults)
                else:
                    try:
                        Note.objects.get(object_id=player.pk,
                                         author_id=request.user.id).delete()
                    except Note.DoesNotExist:
                        pass
        else:
            form = NoteForm()

        data['message'] = 'Note is saved!'
    else:
        data['authenticated'] = False
        redir = request.META.get('HTTP_REFERER')
        data['message'] = utils.anon_alert(request, redir)

    return JsonResponse(data)


def player_positions(request, nhl_id, slug):
    data = {}
    user = request.user
    if user.is_authenticated:
        data['authenticated'] = True
        player = utils.get_player(nhl_id, slug)
        if request.method == 'POST':
            form = PositionsForm(request.POST)
            if form.is_valid():
                checked_data = request.POST.getlist('check')
                if checked_data:
                    defaults = {
                        'data': checked_data,
                        'player_name': player.name,
                    }

                    Position.objects.update_or_create(object_id=player.pk,
                                                      author_id=request.user.id,
                                                      defaults=defaults)
                else:
                    try:
                        Position.objects.get(
                            object_id=player.pk, author_id=request.user.id).delete()
                    except Position.DoesNotExist:
                        pass
        else:
            form = PositionsForm()

        positions_extra = utils.get_object(request, player, Position)
        data_add = {
            'ajax_upd_pos': utils.unpack_list_positions(player, positions_extra),
            'message': 'Positions are saved!',
        }
        data = {**data, **data_add}
    else:
        data['authenticated'] = False
        redir = request.META.get('HTTP_REFERER')
        data['message'] = utils.anon_alert(request, redir)

    return JsonResponse(data)
