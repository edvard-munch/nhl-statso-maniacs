"""Private favorite rows reuse catalogue identity and nullable profile statistics."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .catalogue_serializers import CatalogueMetaSerializer, CataloguePlayerSerializer
from .profile_serializers import StatisticsPacketSerializer


class FavoriteQuotaSerializer(serializers.Serializer):
    limit = serializers.IntegerField()
    skaters_count = serializers.IntegerField()
    goalies_count = serializers.IntegerField()
    total_count = serializers.IntegerField()
    remaining = serializers.IntegerField()
    over_limit = serializers.BooleanField()


class FavoritePlayerSerializer(CataloguePlayerSerializer):
    stats = serializers.SerializerMethodField(allow_null=True)
    availability = serializers.ChoiceField(choices=["complete", "partial", "missing", "unverified"])

    @extend_schema_field(StatisticsPacketSerializer().fields["stats"])
    def get_stats(self, row):
        return row["stats"]


class FavoriteMetaSerializer(CatalogueMetaSerializer):
    quota = FavoriteQuotaSerializer()


class FavoritesResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = FavoritePlayerSerializer(many=True)
    meta = FavoriteMetaSerializer()


class FavoriteMembershipSerializer(serializers.Serializer):
    player_type = serializers.ChoiceField(choices=["skater", "goalie"])
    nhl_id = serializers.IntegerField()
    is_favorite = serializers.BooleanField()
    quota = FavoriteQuotaSerializer()
