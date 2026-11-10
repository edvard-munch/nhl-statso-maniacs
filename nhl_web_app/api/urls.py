"""New API routes are independent of legacy page and AJAX contracts."""

from django.urls import path, re_path
from players.api.views import GameDetailView, ScoreboardView, SeasonsView

from . import schema  # noqa: F401 -- register the OpenAPI authentication extension
from .views import ApiRootView, NotFoundView, SchemaView

app_name = "api_v1"
urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path("schema/", SchemaView.as_view(), name="schema"),
    path("seasons/", SeasonsView.as_view(), name="seasons"),
    path("games/", ScoreboardView.as_view(), name="games"),
    path("games/<int:nhl_id>/", GameDetailView.as_view(), name="game-detail"),
    # Resolve invalid/slashless API paths directly, avoiding HTML debug 404s and
    # CommonMiddleware redirects (especially unsafe-request replay redirects).
    re_path(r"^.*$", NotFoundView.as_view()),
]
