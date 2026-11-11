"""Public profile/history/gamelog shapes without raw stored JSON exposure."""

from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema_field
from rest_framework import serializers

from players.season_stats import GOALIE
from .catalogue import (
    AVERAGES,
    TOTALS,
    SKATER_TOTALS_KIND,
    SKATER_AVERAGES_KIND,
    GOALIE_TOTALS_KIND,
)
from .catalogue_serializers import (
    CataloguePlayerSerializer,
    CatalogueTeamSerializer,
    SeasonIdField,
    SkaterTotalsSerializer,
    SkaterAveragesSerializer,
    GoalieSeasonSerializer,
    CsvField,
    FiniteNumberField,
    QueryBooleanField,
    MAX_FILTER_LENGTH,
    MAX_ORDERING_LENGTH,
)
from .player_logs import ALL_LOG_NUMBERS, numeric_fields, ordering_fields
from .serializers import (
    PaginationQuerySerializer,
    StrictQuerySerializer,
    StrictDateField,
    ScoreboardGameSerializer,
    ScoreboardTeamSerializer,
    SkaterGameStatsSerializer,
    GoalieGameStatsSerializer,
)


class ModeQueryMixin:
    def validate(self, attrs):
        if self.context.get("player_type") == GOALIE and attrs["mode"] == AVERAGES:
            raise serializers.ValidationError({"mode": ["Goalies support mode=totals only."]})
        return attrs


class ProfileQuerySerializer(ModeQueryMixin, StrictQuerySerializer):
    season_id = SeasonIdField(required=False)
    mode = serializers.ChoiceField(choices=[TOTALS, AVERAGES], default=TOTALS)

    def to_internal_value(self, data):
        if "mode" in data and not data["mode"]:
            raise serializers.ValidationError({"mode": ["Supply a nonempty value."]})
        return super().to_internal_value(data)


class HistoryQuerySerializer(ProfileQuerySerializer, PaginationQuerySerializer):
    def get_fields(self):
        fields = super().get_fields()
        fields.pop("season_id")
        return fields


class GamelogQuerySerializer(PaginationQuerySerializer):
    extra_ordering_fields = frozenset()

    season_id = SeasonIdField(
        required=False,
        help_text="Optional regular-season filter from verified saved game IDs. Omission returns all saved dates, not the latest SBS season.",
    )
    date_min = StrictDateField(required=False)
    date_max = StrictDateField(required=False)
    ordering = serializers.CharField(
        default="-date",
        max_length=MAX_ORDERING_LENGTH,
        help_text="Named date/game_id/team_abbr/opponent_abbr or game-statistic fields; '-' descending; unknown values last. Default -date.",
    )
    team = CsvField(required=False, max_length=MAX_FILTER_LENGTH)
    opponent = CsvField(required=False, max_length=MAX_FILTER_LENGTH)

    def get_fields(self):
        fields = super().get_fields()
        for field in sorted(ALL_LOG_NUMBERS):
            for suffix in ("min", "max"):
                fields[field + "_" + suffix] = FiniteNumberField(required=False)
            fields[field + "_isnull"] = QueryBooleanField(required=False)
        return fields

    def to_internal_value(self, data):
        blanks = {key: ["Supply a nonempty value."] for key in data if not data[key]}
        if blanks:
            raise serializers.ValidationError(blanks)
        return super().to_internal_value(data)

    def validate(self, attrs):
        allowed = numeric_fields(self.context.get("player_type"))
        allowed_ordering = (
            ordering_fields(self.context.get("player_type")) | self.extra_ordering_fields
        )
        fields = [term.removeprefix("-") for term in attrs["ordering"].split(",")]
        if any(field not in allowed_ordering for field in fields) or len(set(fields)) != len(
            fields
        ):
            raise serializers.ValidationError(
                {"ordering": ["Use distinct allowlisted fields for this player type."]}
            )
        for field in ALL_LOG_NUMBERS:
            if field not in allowed:
                invalid = {
                    field + "_" + suffix: ["Not available for this player type."]
                    for suffix in ("min", "max", "isnull")
                    if field + "_" + suffix in attrs
                }
                if invalid:
                    raise serializers.ValidationError(invalid)
            low, high = attrs.get(field + "_min"), attrs.get(field + "_max")
            if low is not None and high is not None and low > high:
                raise serializers.ValidationError(
                    {field + "_max": ["Maximum must be greater than or equal to minimum."]}
                )
        if (
            attrs.get("date_min")
            and attrs.get("date_max")
            and attrs["date_min"] > attrs["date_max"]
        ):
            raise serializers.ValidationError(
                {"date_max": ["Maximum must be greater than or equal to minimum."]}
            )
        return attrs


class PublicProfileSerializer(CataloguePlayerSerializer):
    first_name = serializers.CharField()
    birth_city = serializers.CharField()
    birth_state = serializers.CharField()
    birth_country = serializers.CharField()
    birth_country_abbr = serializers.CharField()
    draft_round = serializers.IntegerField(allow_null=True)
    jersey_number = serializers.IntegerField(source="pl_number", allow_null=True)
    nhl_debut = serializers.CharField()
    roster_status = serializers.CharField()
    captain = serializers.BooleanField()
    alternate_captain = serializers.BooleanField(source="alt_captain")
    video_url = serializers.CharField(source="relevant_video")

    def get_fields(self):
        fields = super().get_fields()
        for name in ("teams", "availability", "stats"):
            fields.pop(name)
        return fields


class ProfileSkaterTotalsSerializer(SkaterTotalsSerializer):
    games = serializers.IntegerField(allow_null=True)


class ProfileSkaterAveragesSerializer(SkaterAveragesSerializer):
    games = serializers.IntegerField(allow_null=True)


class ProfileGoalieTotalsSerializer(GoalieSeasonSerializer):
    games = serializers.IntegerField(allow_null=True)


class StatisticsPacketSerializer(serializers.Serializer):
    availability = serializers.ChoiceField(choices=["complete", "partial", "missing", "unverified"])
    stats = serializers.SerializerMethodField(allow_null=True)

    @extend_schema_field(
        PolymorphicProxySerializer(
            component_name="ProfileStatistics",
            serializers={
                SKATER_TOTALS_KIND: ProfileSkaterTotalsSerializer,
                SKATER_AVERAGES_KIND: ProfileSkaterAveragesSerializer,
                GOALIE_TOTALS_KIND: ProfileGoalieTotalsSerializer,
            },
            resource_type_field_name="kind",
        )
    )
    def get_stats(self, packet):
        return packet["stats"]


class ProfileMetaSerializer(serializers.Serializer):
    season_id = serializers.CharField(allow_null=True)
    player_type = serializers.ChoiceField(choices=["skater", "goalie"])
    mode = serializers.ChoiceField(choices=[TOTALS, AVERAGES])


class PlayerProfileSerializer(serializers.Serializer):
    player = PublicProfileSerializer()
    current_team = CatalogueTeamSerializer(allow_null=True)
    selected_season = StatisticsPacketSerializer()
    career_totals = StatisticsPacketSerializer()
    career_averages = StatisticsPacketSerializer(allow_null=True)
    meta = ProfileMetaSerializer()
    seasons_url = serializers.CharField()
    gamelog_url = serializers.CharField()


class TeamContributionSerializer(StatisticsPacketSerializer):
    team = CatalogueTeamSerializer()


class SeasonHistoryEntrySerializer(StatisticsPacketSerializer):
    season_id = serializers.CharField()
    contributions = TeamContributionSerializer(many=True)


class PlayerIdentityMetaSerializer(serializers.Serializer):
    player_type = serializers.ChoiceField(choices=["skater", "goalie"])
    nhl_id = serializers.IntegerField()


class HistoryMetaSerializer(PlayerIdentityMetaSerializer):
    mode = serializers.ChoiceField(choices=[TOTALS, AVERAGES])


class HistoryResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SeasonHistoryEntrySerializer(many=True)
    meta = HistoryMetaSerializer()


class GamelogMetaSerializer(PlayerIdentityMetaSerializer):
    season_id = serializers.CharField(allow_null=True)
    ordering = serializers.CharField()
    date_min = serializers.DateField(allow_null=True)
    date_max = serializers.DateField(allow_null=True)


class GamelogGameSerializer(ScoreboardGameSerializer):
    date = serializers.DateField(allow_null=True)


class GamelogEntrySerializer(serializers.Serializer):
    date = serializers.DateField(allow_null=True)
    game = GamelogGameSerializer(allow_null=True)
    side = serializers.ChoiceField(choices=["away", "home"], allow_null=True)
    team = ScoreboardTeamSerializer(allow_null=True)
    opponent = ScoreboardTeamSerializer(allow_null=True)
    game_position = serializers.CharField(allow_null=True)
    sweater_number = serializers.IntegerField(allow_null=True)
    availability = serializers.ChoiceField(choices=["complete", "partial", "missing", "unverified"])
    stats = serializers.SerializerMethodField()

    @extend_schema_field(
        PolymorphicProxySerializer(
            component_name="GamelogStatistics",
            serializers=[SkaterGameStatsSerializer, GoalieGameStatsSerializer],
            resource_type_field_name=None,
        )
    )
    def get_stats(self, row):
        return row["stats"]


class GamelogResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = GamelogEntrySerializer(many=True)
    meta = GamelogMetaSerializer()
