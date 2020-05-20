from django.conf.urls import include, url
from django.conf import settings
from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('players/', views.players, name='players'),
    path('games/<str:date>/', views.games, name='games'),
    path('games/', views.games, name='games'),
    path('game/<slug>/<int:nhl_id>/', views.game_detail,
         name='game_detail'),
    path('ajax_players/<str:stat_type>/<str:page>/<str:size>/<str:sort_col>/<str:filt_col>/<str:rookie_filt>/<str:checkbox_filt>/',
         views.ajax_players, name='ajax_players'),
    path('ajax_players/<str:stat_type>/<str:page>/<str:size>/<str:sort_col>/<str:filt_col>/<str:rookie_filt>/<str:checkbox_filt>/<str:fav_filt>/',
         views.ajax_players, name='ajax_players'),
    path('favorites/', views.favorites, name='favorites'),
    path('ajax_fav_players_gamelog/<str:stat_type>/<str:page>/<str:size>/<str:sort_col>/<str:filt_col>/',
         views.ajax_fav_players_gamelog, name='jax_fav_players_gamelog'),
    path('player/<slug>/<int:nhl_id>/player_favorite/', views.player_favorite,
         name='player_favorite'),
    path('comparison/', views.comparison, name='comparison'),
    path('player/<slug>/<int:nhl_id>/player_compare/', views.player_compare,
         name='player_compare'),
    path('comparison/reset_comparison/<str:player_type>/', views.reset_comparison, name='reset_comparison'),
    path('search/', views.search, name='search'),
    path('player/<slug>/<int:nhl_id>/', views.player_detail,
         name='player_detail'),
    path('player/<slug>/<int:nhl_id>/gamelog/', views.player_gamelog,
         name='player_gamelog'),
    path('player/<slug>/<int:nhl_id>/player_note/>', views.player_note,
         name='player_note'),
    path('player/<slug>/<int:nhl_id>/player_positions/>', views.player_positions,
         name='player_positions'),
    path('teams/', views.teams, name='teams'),
    path('team/<slug>/<int:team_id>/', views.team_detail,
         name='team_detail'),
    path('ajax_stats_switcher/<slug>/<int:team_id>/<str:stat_type>/<str:pos_filt>/',
         views.ajax_stats_switcher, name='ajax_stats_switcher'),
    path('ajax_comparison_stat_switcher/<str:player_type>/<str:stat_type>/',
         views.ajax_comparison_stat_switcher, name='ajax_comparison_stat_switcher'),
    # url(r'^silk/', include('silk.urls', namespace='silk')),
    url(r'^ajax_calls/search/', views.autocomplete),
    path('auth_callback/', views.auth_callback, name='auth_callback'),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]
