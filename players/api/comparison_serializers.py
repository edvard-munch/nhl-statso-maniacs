"""Comparison query, quota and selected-season/career response contracts."""

from rest_framework import serializers

from .catalogue_serializers import PlayersQuerySerializer, CatalogueMetaSerializer
from .saved_lists import SEASON, CAREER
from .saved_serializers import SavedPlayerSerializer


class ComparisonQuerySerializer(PlayersQuerySerializer):
    scope = serializers.ChoiceField(choices=[SEASON, CAREER], default=SEASON)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["scope"] == CAREER:
            errors = {
                field: ["Not available for scope=career."]
                for field in ("season_id", "team")
                if field in attrs
            }
            if errors:
                raise serializers.ValidationError(errors)
        return attrs


class ComparisonGroupQuotaSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    remaining = serializers.IntegerField()
    over_limit = serializers.BooleanField()


class ComparisonQuotaSerializer(serializers.Serializer):
    limit_per_type = serializers.IntegerField()
    skaters = ComparisonGroupQuotaSerializer()
    goalies = ComparisonGroupQuotaSerializer()


class ComparisonPlayerSerializer(SavedPlayerSerializer):
    pass


class ComparisonMetaSerializer(CatalogueMetaSerializer):
    scope = serializers.ChoiceField(choices=[SEASON, CAREER])
    quota = ComparisonQuotaSerializer()


class ComparisonResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ComparisonPlayerSerializer(many=True)
    meta = ComparisonMetaSerializer()


class ComparisonMembershipSerializer(serializers.Serializer):
    player_type = serializers.ChoiceField(choices=["skater", "goalie"])
    nhl_id = serializers.IntegerField()
    is_compared = serializers.BooleanField()
    quota = ComparisonQuotaSerializer()
