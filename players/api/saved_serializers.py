"""Public identity and nullable profile statistics shared by private saved lists."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .catalogue_serializers import CataloguePlayerSerializer
from .profile_serializers import StatisticsPacketSerializer


class SavedPlayerSerializer(CataloguePlayerSerializer):
    stats = serializers.SerializerMethodField(allow_null=True)
    availability = serializers.ChoiceField(choices=["complete", "partial", "missing", "unverified"])

    @extend_schema_field(StatisticsPacketSerializer().fields["stats"])
    def get_stats(self, row):
        return row["stats"]
