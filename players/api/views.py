"""Public read-only saved-statistics endpoints."""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from nhl_web_app.api.pagination import ApiPagination
from nhl_web_app.api.serializers import ErrorResponseSerializer
from players.seasons import available_seasons, season_label
from .game_detail import game_detail
from .scoreboard import scoreboard
from .serializers import (
    PaginationQuerySerializer,
    SeasonsResponseSerializer,
    SeasonSerializer,
    GameDetailSerializer,
    GameDetailQuerySerializer,
    ScoreboardGameSerializer,
    ScoreboardMetaSerializer,
    ScoreboardQuerySerializer,
    ScoreboardResponseSerializer,
)


@method_decorator(never_cache, name="dispatch")
class ScoreboardView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="scoreboard_list",
        tags=["games"],
        parameters=[ScoreboardQuerySerializer],
        responses={
            status.HTTP_200_OK: ScoreboardResponseSerializer,
            status.HTTP_400_BAD_REQUEST: ErrorResponseSerializer,
            status.HTTP_404_NOT_FOUND: ErrorResponseSerializer,
            status.HTTP_405_METHOD_NOT_ALLOWED: ErrorResponseSerializer,
            status.HTTP_406_NOT_ACCEPTABLE: ErrorResponseSerializer,
            status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorResponseSerializer,
        },
        description="Saved games for an exact NHL schedule date. No writes or NHL requests. Unverified legacy scores are null; score_source identifies verified parsing of stored result text. Page 1 may be empty; other out-of-range pages return 404.",
    )
    def get(self, request):
        query = ScoreboardQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        rows, meta = scoreboard(query.validated_data["date"])
        paginator = ApiPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(
            ScoreboardGameSerializer(page, many=True).data,
            meta=ScoreboardMetaSerializer(meta).data,
        )


@method_decorator(never_cache, name="dispatch")
class GameDetailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="game_retrieve",
        tags=["games"],
        responses={
            status.HTTP_200_OK: GameDetailSerializer,
            status.HTTP_400_BAD_REQUEST: ErrorResponseSerializer,
            status.HTTP_404_NOT_FOUND: ErrorResponseSerializer,
            status.HTTP_405_METHOD_NOT_ALLOWED: ErrorResponseSerializer,
            status.HTTP_406_NOT_ACCEPTABLE: ErrorResponseSerializer,
            status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorResponseSerializer,
        },
        description="Saved game summary and typed, date-specific rosters. Durations are seconds; goalie save_percentage is a fraction. Missing/unverified fields are null. No queries are accepted, no writes or upstream calls occur. An undated saved game has null date and missing player statistics.",
    )
    def get(self, request, nhl_id):
        query = GameDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(GameDetailSerializer(game_detail(nhl_id)).data)


@method_decorator(never_cache, name="dispatch")
class SeasonsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="seasons_list",
        tags=["seasons"],
        parameters=[PaginationQuerySerializer],
        responses={
            status.HTTP_200_OK: SeasonsResponseSerializer,
            status.HTTP_400_BAD_REQUEST: ErrorResponseSerializer,
            status.HTTP_404_NOT_FOUND: ErrorResponseSerializer,
            status.HTTP_405_METHOD_NOT_ALLOWED: ErrorResponseSerializer,
            status.HTTP_406_NOT_ACCEPTABLE: ErrorResponseSerializer,
            status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorResponseSerializer,
        },
        description="Loaded NHL regular-season SBS seasons, newest first, deduplicated across skaters and goalies. Legacy rows without league/game type retain NHL/regular-season defaults. Snapshot fields, averages and the calendar do not establish availability. Default season is global, independent of pagination. No writes or NHL requests. Empty page 1 returns 200; other out-of-range pages return 404.",
    )
    def get(self, request):
        query = PaginationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        seasons = available_seasons()
        paginator = ApiPagination()
        page = paginator.paginate_queryset(seasons, request, view=self)
        rows = [{"season_id": season, "label": season_label(season)} for season in page]
        return paginator.get_paginated_response(
            SeasonSerializer(rows, many=True).data,
            meta={"default_season_id": seasons[0] if seasons else None},
        )
