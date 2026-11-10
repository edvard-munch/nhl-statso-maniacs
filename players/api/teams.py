"""Read saved team identities; selected-season players use the shared catalogue."""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound

from players.models import Team

MAX_TEAM_NHL_ID = 2**31 - 1
DEFAULT_TEAM_ORDERING = "name,nhl_id"
TEAM_ORDERING_FIELDS = frozenset({"name", "abbr", "nhl_id", "conference", "division"})
TEAM_FIELDS = (
    "nhl_id",
    "name",
    "abbr",
    "slug",
    "image",
    "arena_name",
    "arena_location",
    "division",
    "conference",
    "off_site",
    "nhl_debut",
)


def get_team(nhl_id):
    if not 0 < nhl_id <= MAX_TEAM_NHL_ID:
        raise NotFound()
    return get_object_or_404(Team.objects.only(*TEAM_FIELDS), nhl_id=nhl_id)


def team_list(query):
    rows = list(Team.objects.only(*TEAM_FIELDS))
    if "search" in query:
        term = query["search"].casefold()
        rows = [
            team for team in rows if term in team.name.casefold() or term in team.abbr.casefold()
        ]
    for field in ("conference", "division"):
        if field in query:
            rows = [team for team in rows if getattr(team, field) in query[field]]
    ordering = query.get("ordering", DEFAULT_TEAM_ORDERING)
    rows.sort(key=lambda team: team.nhl_id)
    for term in reversed(ordering.split(",")):
        field = term.removeprefix("-")
        rows.sort(key=lambda team: sort_value(getattr(team, field)), reverse=term.startswith("-"))
    return rows, {"ordering": ordering}


def sort_value(value):
    return value.casefold() if isinstance(value, str) else value
