"""Private aggregated favorite gamelogs with the public game's verification contract."""

from rest_framework import serializers, status
from drf_spectacular.utils import extend_schema

from nhl_web_app.api.pagination import ApiPagination
from players.saved_actions import locked_user
from players.season_stats import SKATER, GOALIE
from .catalogue_serializers import MAX_SEARCH_LENGTH
from .favorites import FAVORITE_RELATIONS, quota
from .game_detail import PLAYER_FIELDS
from .player_logs import favorite_gamelogs
from .profile_serializers import GamelogQuerySerializer, GamelogEntrySerializer
from .favorite_serializers import FavoriteQuotaSerializer
from .saved_views import PrivateSavedListView, SAVED_LIST_ERRORS


class FavoriteGamelogQuerySerializer(GamelogQuerySerializer):
    player_type = serializers.ChoiceField(choices=[SKATER, GOALIE], default=SKATER)
    search = serializers.CharField(
        required=False,
        max_length=MAX_SEARCH_LENGTH,
        help_text="Literal case-insensitive favorite player name substring.",
    )

    def validate(self, attrs):
        self.context["player_type"] = attrs["player_type"]
        return super().validate(attrs)


class FavoriteGamelogPlayerSerializer(serializers.Serializer):
    player_type = serializers.ChoiceField(choices=[SKATER, GOALIE])
    nhl_id = serializers.IntegerField()
    name = serializers.CharField()
    last_name = serializers.CharField(allow_blank=True)
    slug = serializers.CharField()
    position_abbr = serializers.CharField()


class FavoriteGamelogEntrySerializer(GamelogEntrySerializer):
    player = FavoriteGamelogPlayerSerializer()


class FavoriteGamelogMetaSerializer(serializers.Serializer):
    player_type = serializers.ChoiceField(choices=[SKATER, GOALIE])
    season_id = serializers.CharField(allow_null=True)
    ordering = serializers.CharField()
    date_min = serializers.DateField(allow_null=True)
    date_max = serializers.DateField(allow_null=True)
    quota = FavoriteQuotaSerializer()


class FavoriteGamelogResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = FavoriteGamelogEntrySerializer(many=True)
    meta = FavoriteGamelogMetaSerializer()


class FavoriteGamelogView(PrivateSavedListView):
    @extend_schema(
        operation_id="me_favorites_gamelog_list",
        tags=["favorites"],
        parameters=[FavoriteGamelogQuerySerializer],
        responses={status.HTTP_200_OK: FavoriteGamelogResponseSerializer, **SAVED_LIST_ERRORS},
        description="Current account's aggregated typed Favorites gamelog, all saved seasons by default. Each row includes explicit player identity. Optional canonical season filters verified regular-season game IDs; date/team/opponent/statistic filters and named ordering precede pagination. Reuses public gamelog/game-detail verification; orphan or ambiguous rows have explicit null statistics, no guesses or snapshot fallback. Literal search filters favorite names. Quotas count both unfiltered favorite groups. Owner-locked reads and serialization, bounded roster queries, no domain writes or NHL calls.",
    )
    def get(self, request):
        query = FavoriteGamelogQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        with locked_user(request.user) as owner:
            players = list(
                getattr(owner, FAVORITE_RELATIONS[params["player_type"]]).only(
                    *PLAYER_FIELDS, "gamelog_stats"
                )
            )
            if "search" in params:
                players = [
                    player
                    for player in players
                    if params["search"].casefold() in player.name.casefold()
                ]
            rows = favorite_gamelogs(players, params["player_type"], params)
            paginator = ApiPagination()
            page = paginator.paginate_queryset(rows, request, view=self)
            data = FavoriteGamelogEntrySerializer(page, many=True).data
            return paginator.get_paginated_response(
                data,
                meta={
                    "player_type": params["player_type"],
                    **{
                        key: params.get(key)
                        for key in ("season_id", "ordering", "date_min", "date_max")
                    },
                    "quota": quota(owner),
                },
            )
