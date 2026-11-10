"""Explicit team metadata and scoped catalogue contracts."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .catalogue_serializers import (
    CatalogueMetaSerializer,
    CataloguePlayerSerializer,
    CatalogueTeamSerializer,
    CsvField,
    MAX_FILTER_LENGTH,
    MAX_ORDERING_LENGTH,
    MAX_SEARCH_LENGTH,
    PlayersQuerySerializer,
    SeasonIdField,
)
from .serializers import PaginationQuerySerializer, StrictQuerySerializer
from .teams import TEAM_ORDERING_FIELDS


class TeamsQuerySerializer(PaginationQuerySerializer):
    search = serializers.CharField(
        required=False,
        max_length=MAX_SEARCH_LENGTH,
        help_text="Literal case-insensitive substring of saved name or abbreviation.",
    )
    conference = CsvField(
        required=False,
        max_length=MAX_FILTER_LENGTH,
        help_text="Exact saved current conference names, comma-separated OR.",
    )
    division = CsvField(
        required=False,
        max_length=MAX_FILTER_LENGTH,
        help_text="Exact saved current division names, comma-separated OR.",
    )
    ordering = serializers.CharField(
        required=False,
        max_length=MAX_ORDERING_LENGTH,
        help_text="name, abbr, nhl_id, conference or division; '-' descending; default name,nhl_id. NHL ID breaks ties.",
    )

    def to_internal_value(self, data):
        blanks = {key: ["Supply a nonempty value."] for key in data if data[key] == ""}
        if blanks:
            raise serializers.ValidationError(blanks)
        return super().to_internal_value(data)

    def validate_ordering(self, ordering):
        fields = [term.removeprefix("-") for term in ordering.split(",")]
        if any(field not in TEAM_ORDERING_FIELDS for field in fields) or len(set(fields)) != len(
            fields
        ):
            raise serializers.ValidationError("Use distinct allowlisted ordering fields.")
        return ordering


class TeamDetailQuerySerializer(StrictQuerySerializer):
    season_id = SeasonIdField(
        required=False,
        help_text="Consecutive eight-digit ID; omission selects newest loaded SBS season across both player types.",
    )


class TeamPlayersQuerySerializer(PlayersQuerySerializer):
    def get_fields(self):
        fields = super().get_fields()
        fields.pop("team")
        return fields


class TeamSerializer(serializers.Serializer):
    nhl_id = serializers.IntegerField()
    name = serializers.CharField()
    abbr = serializers.CharField()
    slug = serializers.CharField()
    image_url = serializers.SerializerMethodField()
    arena_name = serializers.CharField()
    arena_location = serializers.CharField()
    division = serializers.CharField()
    conference = serializers.CharField()
    website_url = serializers.CharField(source="off_site")
    nhl_debut = serializers.CharField()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_image_url(self, team):
        return team.image.url if team.image else None


class TeamsMetaSerializer(serializers.Serializer):
    ordering = serializers.CharField()


class TeamsResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = TeamSerializer(many=True)
    meta = TeamsMetaSerializer()


class TeamSeasonMetaSerializer(serializers.Serializer):
    season_id = serializers.CharField(allow_null=True)


class TeamDetailSerializer(serializers.Serializer):
    team = TeamSerializer()
    meta = TeamSeasonMetaSerializer()
    players_url = serializers.CharField(
        help_text="API path for paginated team contributions, preserving the resolved season when known."
    )


class TeamPlayerSerializer(CataloguePlayerSerializer):
    jersey_number = serializers.IntegerField(
        source="_player.pl_number",
        allow_null=True,
        help_text="Current profile jersey number; not reconstructed for the selected season.",
    )


class TeamPlayersMetaSerializer(CatalogueMetaSerializer):
    team = CatalogueTeamSerializer()


class TeamPlayersResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = TeamPlayerSerializer(many=True)
    meta = TeamPlayersMetaSerializer()
