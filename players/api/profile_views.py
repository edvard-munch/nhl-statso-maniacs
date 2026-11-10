"""Public typed profile and history reads; legacy pages retain their contracts."""

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from nhl_web_app.api.pagination import ApiPagination
from nhl_web_app.api.serializers import ErrorResponseSerializer
from .catalogue import resolve_season
from .player_logs import gamelog
from .profiles import get_player, history, profile
from .profile_serializers import (
    ProfileQuerySerializer,
    PlayerProfileSerializer,
    HistoryQuerySerializer,
    HistoryResponseSerializer,
    SeasonHistoryEntrySerializer,
    GamelogQuerySerializer,
    GamelogEntrySerializer,
    GamelogResponseSerializer,
)

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
TYPED_PATH = OpenApiParameter(
    "player_type", str, OpenApiParameter.PATH, enum=["skater", "goalie"], required=True
)


@method_decorator(never_cache, name="dispatch")
class PublicPlayerView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class PlayerProfileView(PublicPlayerView):
    @extend_schema(
        operation_id="player_retrieve",
        tags=["players"],
        parameters=[TYPED_PATH, ProfileQuerySerializer],
        responses={status.HTTP_200_OK: PlayerProfileSerializer, **READ_ERRORS},
        description="Typed saved public biography, current team, selected SBS season and separate saved career totals/averages. Missing/ambiguous statistics remain explicit; zero-game profiles remain available. No private data, snapshot fallback, writes or NHL calls. Linked season history and gamelog are paginated separately.",
    )
    def get(self, request, player_type, nhl_id):
        query = ProfileQuerySerializer(
            data=request.query_params, context={"player_type": player_type}
        )
        query.is_valid(raise_exception=True)
        player = get_player(player_type, nhl_id, resource="profile")
        data = profile(
            player, player_type, resolve_season(query.validated_data), query.validated_data["mode"]
        )
        kwargs = {"player_type": player_type, "nhl_id": nhl_id}
        data["seasons_url"] = (
            reverse("api_v1:player-seasons", kwargs=kwargs)
            + "?"
            + urlencode({"mode": query.validated_data["mode"]})
        )
        data["gamelog_url"] = reverse("api_v1:player-gamelog", kwargs=kwargs)
        return Response(PlayerProfileSerializer(data).data)


class PlayerSeasonsView(PublicPlayerView):
    @extend_schema(
        operation_id="player_seasons_list",
        tags=["players"],
        parameters=[TYPED_PATH, HistoryQuerySerializer],
        responses={status.HTTP_200_OK: HistoryResponseSerializer, **READ_ERRORS},
        description="Saved NHL regular-season SBS history newest first, one entry per season with overall statistics and exact team contributions. Totals/averages use the shared reader; ambiguous rows remain unverified, no snapshot or saved SBS-average fallback. Empty page 1 is 200; later out-of-range pages are 404. Biography is current; season history is not a career aggregate.",
    )
    def get(self, request, player_type, nhl_id):
        query = HistoryQuerySerializer(
            data=request.query_params, context={"player_type": player_type}
        )
        query.is_valid(raise_exception=True)
        player = get_player(player_type, nhl_id, resource="history")
        rows = history(player, player_type, query.validated_data["mode"])
        paginator = ApiPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(
            SeasonHistoryEntrySerializer(page, many=True).data,
            meta={
                "player_type": player_type,
                "nhl_id": nhl_id,
                "mode": query.validated_data["mode"],
            },
        )


class PlayerGamelogView(PublicPlayerView):
    @extend_schema(
        operation_id="player_gamelog_list",
        tags=["players"],
        parameters=[TYPED_PATH, GamelogQuerySerializer],
        responses={status.HTTP_200_OK: GamelogResponseSerializer, **READ_ERRORS},
        description="Saved dated gamelog and linked game roster evidence. Omitted season means all saved games; optional canonical season filters verified regular-season game IDs. Reuses game-detail identity/legacy collision checks; orphan rows are unverified with null statistics. Filters precede pagination, dates newest first by default, unknown dates last. Durations are seconds and save_percentage a fraction. No private state, writes or NHL calls.",
    )
    def get(self, request, player_type, nhl_id):
        query = GamelogQuerySerializer(
            data=request.query_params, context={"player_type": player_type}
        )
        query.is_valid(raise_exception=True)
        player = get_player(player_type, nhl_id, resource="gamelog")
        rows = gamelog(player, player_type, query.validated_data)
        paginator = ApiPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        meta = {
            "player_type": player_type,
            "nhl_id": nhl_id,
            **{
                key: query.validated_data.get(key)
                for key in ("season_id", "ordering", "date_min", "date_max")
            },
        }
        return paginator.get_paginated_response(
            GamelogEntrySerializer(page, many=True).data, meta=meta
        )
