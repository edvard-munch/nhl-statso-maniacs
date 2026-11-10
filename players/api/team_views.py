"""Public team reads without templates, private state, writes or NHL calls."""

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from nhl_web_app.api.pagination import ApiPagination
from nhl_web_app.api.serializers import ErrorResponseSerializer
from .catalogue import catalogue, resolve_season
from .catalogue_serializers import CatalogueTeamSerializer
from .team_serializers import (
    TeamDetailQuerySerializer,
    TeamDetailSerializer,
    TeamPlayersQuerySerializer,
    TeamPlayerSerializer,
    TeamPlayersResponseSerializer,
    TeamSerializer,
    TeamsQuerySerializer,
    TeamsResponseSerializer,
)
from .teams import get_team, team_list

READ_ERRORS = {
    code: ErrorResponseSerializer
    for code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_405_METHOD_NOT_ALLOWED,
        status.HTTP_406_NOT_ACCEPTABLE,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
}


@method_decorator(never_cache, name="dispatch")
class TeamsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="teams_list",
        tags=["teams"],
        parameters=[TeamsQuerySerializer],
        responses={status.HTTP_200_OK: TeamsResponseSerializer, **READ_ERRORS},
        description="All saved team identities, including historical or empty teams. Metadata is current; no season/active status is inferred. Named filtering/ordering precedes pagination. No writes or upstream calls. Empty page 1 is 200; other out-of-range pages are 404.",
    )
    def get(self, request):
        query = TeamsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        rows, meta = team_list(query.validated_data)
        paginator = ApiPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(TeamSerializer(page, many=True).data, meta=meta)


@method_decorator(never_cache, name="dispatch")
class TeamDetailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="team_retrieve",
        tags=["teams"],
        parameters=[TeamDetailQuerySerializer],
        responses={status.HTTP_200_OK: TeamDetailSerializer, **READ_ERRORS},
        description="Saved current team identity with resolved selected season and a paginated contributions link. No snapshot/roster inference, writes or NHL calls. A known team remains available without players or seasons.",
    )
    def get(self, request, nhl_id):
        query = TeamDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        team = get_team(nhl_id)
        season = resolve_season(query.validated_data)
        players_url = reverse("api_v1:team-players", kwargs={"nhl_id": team.nhl_id})
        if season is not None:
            players_url += "?" + urlencode({"season_id": season})
        return Response(
            TeamDetailSerializer(
                {
                    "team": team,
                    "meta": {"season_id": season},
                    "players_url": players_url,
                }
            ).data
        )


@method_decorator(never_cache, name="dispatch")
class TeamPlayersView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="team_players_list",
        tags=["teams"],
        parameters=[TeamPlayersQuerySerializer],
        responses={status.HTTP_200_OK: TeamPlayersResponseSerializer, **READ_ERRORS},
        description="Selected team's exact NHL regular-season SBS contributions, positive known games only. Reuses Players filters, ordering, pagination and typed statistics, excluding the team query parameter. Combined-only rows and current roster links never substitute for missing team splits. Biography/position/jersey metadata is current. No writes, private fields or upstream calls. Empty page 1 is 200; other out-of-range pages are 404.",
    )
    def get(self, request, nhl_id):
        query = TeamPlayersQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        team = get_team(nhl_id)
        rows, meta = catalogue(query.validated_data, team=team)
        meta["team"] = CatalogueTeamSerializer(team).data
        paginator = ApiPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(
            TeamPlayerSerializer(page, many=True, context={"mode": meta["mode"]}).data,
            meta=meta,
        )
