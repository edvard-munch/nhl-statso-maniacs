"""Public read-only scoreboard endpoint."""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from nhl_web_app.api.pagination import ApiPagination
from nhl_web_app.api.serializers import ErrorResponseSerializer
from .game_detail import game_detail
from .scoreboard import scoreboard
from .serializers import (
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
