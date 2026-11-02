import json
import os
from itertools import chain

from django.core import serializers
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from . import player_table, saved_players, team_tables, utils
from .forms import NoteForm, PositionsForm
from .models import Game, Gameday, Goalie, Note, Position, Skater, Team


def home(request):
    return render(request, "players/home.html", {"title": "Home"})


def about(request):
    return render(request, "players/about.html", {"title": "About"})


def games(request, date=utils.get_us_pacific_date()):
    context = {}
    gamedays = list(Gameday.objects.all().order_by("day"))
    try:
        today = Gameday.objects.get(day=date)
    except Gameday.DoesNotExist:
        today = Gameday.objects.last()
    days_per_page = utils.get_adjacent(gamedays, today, utils.GAMES_PER_PAGE)

    context = {
        "today": today,
        "days_per_page": days_per_page,
    }

    return render(request, "players/games.html", context)


def game_detail(request, slug, nhl_id):
    game = Game.objects.get(nhl_id=nhl_id, slug=slug)
    user = request.user

    context = {
        "game": game,
        "skaters": [
            {
                "header": game.side_set.get(side="away").team,
                "list": game.away_forwards.all().order_by(*utils.GAME_PLAYERS_SORT_ORDER),
                "type": utils.FRW,
                "table_id": utils.TABLE_IDS[3],
            },
            {
                "list": game.away_defencemen.all().order_by(*utils.GAME_PLAYERS_SORT_ORDER),
                "type": utils.DEF,
                "table_id": utils.TABLE_IDS[2],
                "game_goalies_table": {
                    "template": utils.TEMPLATES[8],
                    "list": game.away_goalies.all(),
                },
                "whitespace": utils.WHITESPACE,
            },
            {
                "header": game.side_set.get(side="home").team,
                "list": game.home_forwards.all().order_by(*utils.GAME_PLAYERS_SORT_ORDER),
                "type": utils.FRW,
                "table_id": utils.TABLE_IDS[5],
            },
            {
                "list": game.home_defencemen.all().order_by(*utils.GAME_PLAYERS_SORT_ORDER),
                "type": utils.DEF,
                "table_id": utils.TABLE_IDS[4],
                "game_goalies_table": {
                    "template": utils.TEMPLATES[8],
                    "list": game.home_goalies.all(),
                },
                "whitespace": utils.WHITESPACE,
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
        fav_players = list(
            chain(
                fav_away_goalies,
                fav_home_goalies,
                fav_away_defencemen,
                fav_home_defencemen,
                fav_away_forwards,
                fav_home_forwards,
            )
        )

        context["favorites"] = fav_players

    return render(request, "players/game_detail.html", context)


def auth_callback(request):
    context = {
        "title": "auth_callback",
        "code": request.GET.get("code"),
    }

    return render(request, "auth_callback.html", context)


def players(request):
    try:
        selection = player_table.season_context(request.GET.get("season"))
    except ValueError as error:
        return HttpResponseBadRequest(str(error), content_type="text/plain")
    context = {
        "title": "Players",
        "options": utils.PAGE_SIZE_OPTIONS,
        "table_page_size": utils.PAGE_SIZE_2,
        **selection,
    }

    return render(request, "players/players.html", context)


def favorites(request):
    context = {}
    user = request.user
    if user.is_authenticated:
        try:
            context.update(player_table.season_context(request.GET.get("season")))
        except ValueError as error:
            return HttpResponseBadRequest(str(error), content_type="text/plain")
        fav_goalies = user.favorite_goalies.select_related("team")
        fav_skaters = user.favorite_skaters.select_related("team")
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

        context.update(
            {
                "favorites_g": fav_goalies,
                "favorites_s": fav_skaters,
                "numb_of_goalies": numb_of_goalies,
                "numb_of_skaters": numb_of_skaters,
                "table_page_size": utils.PAGE_SIZE_2,
                "skaters_options": skaters_options,
                "goalies_options": goalies_options,
                "skaters_games_options": skaters_games_options,
                "goalies_games_options": goalies_games_options,
            }
        )

    return render(request, "players/favorites.html", context)


def ajax_fav_players_gamelog(request, stat_type, page, size, sort_col, filt_col):
    page = utils.parse_url_param(page)
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"authenticated": False, "error": "Sign in required"}, status=403)
    if stat_type not in (utils.STAT_TYPES[3], utils.STAT_TYPES[4]):
        return JsonResponse({"error": "Invalid gamelog type"}, status=400)
    if user.is_authenticated:
        if stat_type == utils.STAT_TYPES[3]:
            fav_players = user.favorite_skaters.select_related("team")
            columns = utils.COLUMNS_SKATERS_GAMELOG
        elif stat_type == utils.STAT_TYPES[4]:
            fav_players = user.favorite_goalies.select_related("team")
            columns = utils.COLUMNS_GOALIES_GAMELOG

        all_games = utils.favorite_players_gamelog(fav_players)

        if utils.ALL_ROWS in size.lower():
            size = len(all_games)
        else:
            size = utils.parse_url_param(size)

        start = int(size) * (int(page) - 1)
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


def get_latest_loaded_season_id():
    skater_season = (
        Skater.objects.exclude(stats_season_id__isnull=True)
        .exclude(stats_season_id="")
        .order_by("-stats_season_id")
        .values_list("stats_season_id", flat=True)
        .first()
    )
    goalie_season = (
        Goalie.objects.exclude(stats_season_id__isnull=True)
        .exclude(stats_season_id="")
        .order_by("-stats_season_id")
        .values_list("stats_season_id", flat=True)
        .first()
    )

    seasons = [season for season in [skater_season, goalie_season] if season]
    if not seasons:
        return None

    return max(seasons)


def ajax_players(
    request, stat_type, page, size, sort_col, filt_col, rookie_filt, checkbox_filt, fav_filt=None
):
    collection = player_table.FAVORITES if fav_filt else None
    if collection and not request.user.is_authenticated:
        return JsonResponse({"authenticated": False, "error": "Sign in required"}, status=403)
    try:
        season = player_table.selected_season(request.GET.get("season"))
        data = player_table.build_table(
            request,
            season,
            stat_type,
            page,
            size,
            sort_col,
            filt_col,
            rookie_filt,
            checkbox_filt,
            collection,
        )
    except (ValueError, TypeError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse(data)


def search(request):
    if "q" in request.GET and request.GET["q"]:
        query = request.GET["q"].strip()

        result_skaters = Skater.objects.filter(name__icontains=query)
        result_goalies = Goalie.objects.filter(name__icontains=query)
        result_teams = Team.objects.filter(name__icontains=query)
        result_players = list(chain(result_skaters, result_goalies))

        context = {
            "players": result_players,
            "query": query,
            "teams": result_teams,
        }

        user = request.user
        if user.is_authenticated:
            context_extra = {
                "favorites_g": result_goalies.filter(favoriting__username=user),
                "favorites_s": result_skaters.filter(favoriting__username=user),
                "compare_g": result_goalies.filter(comparing__username=user),
                "compare_s": result_skaters.filter(comparing__username=user),
            }

            context = {**context, **context_extra}
        return render(request, "players/search_results.html", context)

    return HttpResponse("Please submit a search term.")


def autocomplete(request):
    query = request.GET.get("term", "").strip()

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
            link = os.path.join("//", domain, f"search?q={query}")
            href = f'href="{link}">{utils.SEARCH_RES_FULL}'
            data[index]["label"] = f'<a class="{utils.AUTOSEARCH_CSS_TOTAL}"{href}</a>'
            data[index]["value"] = utils.SEARCH_RES_FULL
        elif res == utils.SEARCH_RES_DELIMETER:
            data[index]["label"] = res

        else:
            if isinstance(res, Team):
                url_mid_part = utils.TEAM_URL
                css_class = utils.AUTOSEARCH_CSS_TEAM
            else:
                url_mid_part = utils.PLAYER_URL
                css_class = utils.AUTOSEARCH_CSS_PLAYER

            link = os.path.join("//", domain, url_mid_part, res.slug, str(res.nhl_id))
            href = f'href="{link}">{res.name}'
            data[index]["label"] = f'<a class="{css_class}"{href}</a>'
            data[index]["value"] = res.name

    return JsonResponse(data)


def player_detail(request, slug, nhl_id):
    player = utils.get_player(nhl_id, slug)
    current_season_id = get_latest_loaded_season_id()
    show_current_stats = bool(
        player.games
        and player.stats_season_id
        and current_season_id
        and player.stats_season_id == current_season_id
    )
    user = request.user
    if user.is_authenticated:
        if utils.measurements_format_is_euro(user):
            player = utils.adjust_measurements(player)

    skater = player.position_abbr in utils.POSITIONS[1:]
    slicer = slice(utils.LAST_GAMES_TO_SHOW)

    context = {
        "player": player,
        # for a goalie
        "sbs_stats": player.sbs_stats,
        "total": player.career_stats,
        # for a skater
        "stats": [
            {
                "stats": player.sbs_stats,
                "title": "Career",
                "total": player.career_stats,
            },
        ],
        "last_gms": utils.get_gamelog(player, slicer),
        "proj_stats": utils.season_in_prog() and player.proj_stats,
        "note": utils.get_object(request, player, Note),
        "skater": skater,
        "show_current_stats": show_current_stats,
        "note_max_length": Note._meta.get_field("text").max_length,
    }

    if skater:
        avg_dict = {
            "stats": player.sbs_stats_avg,
            "title": "Career averages",
            "total": player.career_stats_avg,
        }
        context["stats"].append(avg_dict)

        positions_extra = utils.get_object(request, player, Position)
        context["checked_dict"] = utils.get_checked_dict(player, positions_extra)
        context["positions"] = utils.unpack_list_positions(player, positions_extra)

    context = {
        **context,
        **utils.add_comp_info(request, player),
        **utils.add_fav_info(request, player),
    }

    return render(request, "players/player_detail.html", context)


def player_gamelog(request, slug, nhl_id):
    player = utils.get_player(nhl_id, slug)
    gamelog = utils.get_gamelog(player)
    options = utils.PAGE_SIZE_OPTIONS
    gamelog_size = len(gamelog)
    gamelog_options = [option for option in options if option < gamelog_size]

    context = {
        "player": player,
        "gamelog": gamelog,
        "gamelog_options": gamelog_options,
        "pager": gamelog_size > utils.PAGE_SIZE_2,
    }

    return render(request, "players/player_gamelog.html", context)


def teams(request):
    context = {
        "teams": Team.objects.all().order_by("name"),
    }

    return render(request, "players/teams.html", context)


def team_detail(request, slug, team_id):
    team = get_object_or_404(Team, nhl_id=team_id, slug=slug)
    try:
        selection = player_table.season_context(request.GET.get("season"))
    except ValueError as error:
        return HttpResponseBadRequest(str(error), content_type="text/plain")
    context = team_tables.get_team_detail_context(
        team, request.user, selection["season_id"] or None
    )
    context.update(selection)
    return render(request, "players/team_detail.html", context)


def ajax_stats_switcher(request, slug, team_id, stat_type, pos_filt):
    team = get_object_or_404(Team, nhl_id=team_id, slug=slug)
    try:
        if pos_filt not in (team_tables.DEFENCEMEN, team_tables.FORWARDS, team_tables.ALL_SKATERS):
            raise ValueError("Invalid team position filter")
        season = player_table.selected_season(request.GET.get("season"))
        context = team_tables.get_team_detail_context(team, request.user, season, stat_type)
        context["object"] = team_tables.skater_group(context, pos_filt)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse(
        {
            "stats": render_to_string(context["tbody_skaters"], context=context, request=request),
            "season_id": season,
            "season_label": player_table.season_label(season),
            "stat_type": stat_type,
            "position_filter": pos_filt,
            "total": len(context["object"]["list"]),
            "empty_message": team_tables.empty_message(team, season, pos_filt),
        }
    )


def ajax_comparison_stat_switcher(request, player_type, stat_type):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False, "error": "Sign in required"}, status=403)
    try:
        if (
            player_type not in saved_players.ALLOWED_MODES
            or stat_type not in saved_players.ALLOWED_MODES[player_type]
        ):
            raise ValueError("Invalid comparison statistics mode")
        season, skater_mode, goalie_mode = saved_players.selection(request)
        if player_type == saved_players.SKATERS:
            skater_mode = stat_type
        else:
            goalie_mode = stat_type
        context = saved_players.comparison_context(request.user, season, skater_mode, goalie_mode)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    rows = context["skater_rows" if player_type == saved_players.SKATERS else "goalie_rows"]
    base = "players/partial_{}_comparison_base.html".format(player_type)
    return JsonResponse(
        {
            "stats": render_to_string(
                "players/partial_comparison_statistics.html",
                {"comparison_rows": rows},
                request=request,
            ),
            "table": render_to_string(base, context, request=request),
            "season_id": season,
            "stat_type": stat_type,
            "player_type": player_type,
        }
    )


def comparison(request):
    context = {}
    if request.user.is_authenticated:
        try:
            selection = player_table.season_context(request.GET.get("season"))
            season, skater_mode, goalie_mode = saved_players.selection(request)
            context = saved_players.comparison_context(
                request.user, season, skater_mode, goalie_mode
            )
            context.update(selection)
        except ValueError as error:
            return HttpResponseBadRequest(str(error), content_type="text/plain")
    return render(request, "players/comparison.html", context)


def player_compare(request, slug, nhl_id):
    data = {}
    user = request.user
    if user.is_authenticated:
        try:
            season, skater_mode, goalie_mode = saved_players.selection(request)
        except ValueError as error:
            return JsonResponse({"error": str(error)}, status=400)
        data["authenticated"] = True
        player = utils.get_player(nhl_id, slug)
        if isinstance(player, Goalie):
            quota = user.comparable_goalies.count()
        else:
            quota = user.comparable_skaters.count()

        if player.comparing.filter(id=user.id).exists():
            player.comparing.remove(user)
            data["message"] = f"{player.name} successfully removed from the comparison"
            utils.pop_key(data, "comp_quota_reached")
        else:
            if quota < utils.COMPARISON_QUOTA:
                player.comparing.add(user)
                data["message"] = f"{player.name} successfully added to the comparison"
                utils.pop_key(data, "comp_quota_reached")

            else:
                data["message"] = f"Comparison quota reached ({utils.COMPARISON_QUOTA} players)"
                data["comp_quota_reached"] = 1
        context = saved_players.comparison_context(user, season, skater_mode, goalie_mode)
        data.update(saved_players.comparison_payload(context, request))
    else:
        data["authenticated"] = False
        redir = request.META.get("HTTP_REFERER")
        data["message"] = utils.anon_alert(request, redir)

    return JsonResponse(data)


def reset_comparison(request, player_type):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False, "error": "Sign in required"}, status=403)
    try:
        if player_type not in saved_players.ALLOWED_MODES:
            raise ValueError("Invalid comparison player type")
        season, skater_mode, goalie_mode = saved_players.selection(request)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    getattr(request.user, "comparable_" + player_type).clear()
    context = saved_players.comparison_context(request.user, season, skater_mode, goalie_mode)
    return JsonResponse(saved_players.comparison_payload(context, request))


def player_favorite(request, slug, nhl_id):
    data = {}
    user = request.user
    if user.is_authenticated:
        data["authenticated"] = True
        quota = user.favorite_skaters.count() + user.favorite_goalies.count()
        player = utils.get_player(nhl_id, slug)
        if player.favoriting.filter(id=user.id).exists():
            player.favoriting.remove(user)
            data["message"] = f"{player.name} successfully removed from the favorites"
            utils.pop_key(data, "fav_quota_reached")
            data["skaters_count"] = user.favorite_skaters.count()
            data["goalies_count"] = user.favorite_goalies.count()
        else:
            if quota < utils.FAVORITES_QUOTA:
                player.favoriting.add(user)
                data["message"] = f"{player.name} successfully added to the favorites"
                utils.pop_key(data, "fav_quota_reached")
            else:
                data["message"] = f"Favorites quota reached ({utils.FAVORITES_QUOTA} players)"
                data["fav_quota_reached"] = 1
    else:
        data["authenticated"] = False
        redir = request.META.get("HTTP_REFERER")
        data["message"] = utils.anon_alert(request, redir)

    return JsonResponse(data)


def player_note(request, slug, nhl_id):
    data = {}
    user = request.user
    if user.is_authenticated:
        data["authenticated"] = True
        player = utils.get_player(nhl_id, slug)
        if request.method == "POST":
            form = NoteForm(request.POST)
            if form.is_valid():
                text = form.cleaned_data["text"]
                if text:
                    defaults = {
                        "text": text,
                        "player_name": player.name,
                    }

                    Note.objects.update_or_create(
                        object_id=player.pk, author_id=request.user.id, defaults=defaults
                    )
                else:
                    try:
                        Note.objects.get(object_id=player.pk, author_id=request.user.id).delete()
                    except Note.DoesNotExist:
                        pass
        else:
            form = NoteForm()

        data["message"] = "Note is saved!"
    else:
        data["authenticated"] = False
        redir = request.META.get("HTTP_REFERER")
        data["message"] = utils.anon_alert(request, redir)

    return JsonResponse(data)


def player_positions(request, nhl_id, slug):
    data = {}
    user = request.user
    if user.is_authenticated:
        data["authenticated"] = True
        player = utils.get_player(nhl_id, slug)
        if request.method == "POST":
            form = PositionsForm(request.POST)
            if form.is_valid():
                checked_data = request.POST.getlist("check")
                if checked_data:
                    defaults = {
                        "data": checked_data,
                        "player_name": player.name,
                    }

                    Position.objects.update_or_create(
                        object_id=player.pk, author_id=request.user.id, defaults=defaults
                    )
                else:
                    try:
                        Position.objects.get(
                            object_id=player.pk, author_id=request.user.id
                        ).delete()
                    except Position.DoesNotExist:
                        pass
        else:
            form = PositionsForm()

        positions_extra = utils.get_object(request, player, Position)
        data_add = {
            "ajax_upd_pos": utils.unpack_list_positions(player, positions_extra),
            "message": "Positions are saved!",
        }
        data = {**data, **data_add}
    else:
        data["authenticated"] = False
        redir = request.META.get("HTTP_REFERER")
        data["message"] = utils.anon_alert(request, redir)

    return JsonResponse(data)
