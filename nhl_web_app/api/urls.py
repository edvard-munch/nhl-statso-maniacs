"""New API routes are independent of legacy page and AJAX contracts."""

from django.urls import path, re_path
from players.api.comparison_views import (
    ComparisonView,
    ComparisonMembershipView,
    ComparisonGroupView,
)
from players.api.owned_player_data import PrivateNoteView, PrivatePositionsView
from players.api.favorite_gamelogs import FavoriteGamelogView
from players.api.favorite_views import FavoritesView, FavoriteMembershipView
from players.api.profile_views import PlayerProfileView, PlayerSeasonsView, PlayerGamelogView
from players.api.team_views import TeamDetailView, TeamPlayersView, TeamsView
from players.api.views import GameDetailView, ScoreboardView, SeasonsView, PlayersView

from .account import AccountView
from .registration import RegistrationView
from .password_recovery import (
    PasswordRecoveryRequestView,
    PasswordRecoveryConfirmView,
    ResetLinkView,
)
from .auth_views import CsrfView, SessionView, LoginView, LogoutView
from . import schema  # noqa: F401 -- register the OpenAPI authentication extension
from .views import ApiRootView, NotFoundView, SchemaView

app_name = "api_v1"
urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path("auth/password-reset/", PasswordRecoveryRequestView.as_view(), name="password-reset"),
    path("auth/password-reset/validate/", ResetLinkView.as_view(), name="password-reset-validate"),
    path(
        "auth/password-reset/confirm/",
        PasswordRecoveryConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("auth/register/", RegistrationView.as_view(), name="auth-register"),
    path("auth/csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("auth/session/", SessionView.as_view(), name="auth-session"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", AccountView.as_view(), name="account"),
    path("schema/", SchemaView.as_view(), name="schema"),
    path(
        "me/players/<str:player_type>/<int:nhl_id>/note/",
        PrivateNoteView.as_view(),
        name="player-note",
    ),
    path(
        "me/players/<str:player_type>/<int:nhl_id>/positions/",
        PrivatePositionsView.as_view(),
        name="player-positions",
    ),
    path("me/comparison/", ComparisonView.as_view(), name="comparison"),
    path(
        "me/comparison/<str:player_type>/", ComparisonGroupView.as_view(), name="comparison-group"
    ),
    path(
        "me/comparison/<str:player_type>/<int:nhl_id>/",
        ComparisonMembershipView.as_view(),
        name="comparison-membership",
    ),
    path("me/favorites/gamelog/", FavoriteGamelogView.as_view(), name="favorites-gamelog"),
    path("me/favorites/", FavoritesView.as_view(), name="favorites"),
    path(
        "me/favorites/<str:player_type>/<int:nhl_id>/",
        FavoriteMembershipView.as_view(),
        name="favorite-membership",
    ),
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
