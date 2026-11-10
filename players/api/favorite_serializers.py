"""Private favorite rows reuse catalogue identity and nullable profile statistics."""

from rest_framework import serializers

from .catalogue_serializers import CatalogueMetaSerializer
from .saved_serializers import SavedPlayerSerializer


class FavoriteQuotaSerializer(serializers.Serializer):
    limit = serializers.IntegerField()
    skaters_count = serializers.IntegerField()
    goalies_count = serializers.IntegerField()
    total_count = serializers.IntegerField()
    remaining = serializers.IntegerField()
    over_limit = serializers.BooleanField()


class FavoritePlayerSerializer(SavedPlayerSerializer):
    pass


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
