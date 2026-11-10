"""New API routes are independent of legacy page and AJAX contracts."""

from django.urls import path, re_path
from players.api.profile_views import PlayerProfileView, PlayerSeasonsView, PlayerGamelogView
from players.api.team_views import TeamDetailView, TeamPlayersView, TeamsView
from players.api.views import GameDetailView, ScoreboardView, SeasonsView, PlayersView

from .registration import RegistrationView
from .auth_views import CsrfView, SessionView, LoginView, LogoutView
from . import schema  # noqa: F401 -- register the OpenAPI authentication extension
from .views import ApiRootView, NotFoundView, SchemaView

app_name = "api_v1"
urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path("auth/register/", RegistrationView.as_view(), name="auth-register"),
    path("auth/csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("auth/session/", SessionView.as_view(), name="auth-session"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("schema/", SchemaView.as_view(), name="schema"),
    path("teams/", TeamsView.as_view(), name="teams"),
    path("teams/<int:nhl_id>/", TeamDetailView.as_view(), name="team-detail"),
    path("teams/<int:nhl_id>/players/", TeamPlayersView.as_view(), name="team-players"),
    path(
        "players/<str:player_type>/<int:nhl_id>/", PlayerProfileView.as_view(), name="player-detail"
    ),
    path(
        "players/<str:player_type>/<int:nhl_id>/seasons/",
        PlayerSeasonsView.as_view(),
        name="player-seasons",
    ),
    path(
        "players/<str:player_type>/<int:nhl_id>/gamelog/",
        PlayerGamelogView.as_view(),
        name="player-gamelog",
    ),
    path("players/", PlayersView.as_view(), name="players"),
    path("seasons/", SeasonsView.as_view(), name="seasons"),
    path("games/", ScoreboardView.as_view(), name="games"),
    path("games/<int:nhl_id>/", GameDetailView.as_view(), name="game-detail"),
    # Resolve invalid/slashless API paths directly, avoiding HTML debug 404s and
    # CommonMiddleware redirects (especially unsafe-request replay redirects).
    re_path(r"^.*$", NotFoundView.as_view()),
]
