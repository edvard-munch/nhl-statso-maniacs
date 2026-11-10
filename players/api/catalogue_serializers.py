"""Allowlisted public catalogue parameters and typed season response variants."""

import math
import re

from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema_field
from rest_framework import serializers

from players.season_stats import GOALIE, SKATER, normalize_season_id
from .catalogue import (
    ALL_NUMBERS,
    AVERAGES,
    GOALIE_COUNTS,
    SKATER_TOTALS_KIND,
    SKATER_AVERAGES_KIND,
    GOALIE_TOTALS_KIND,
    GOALIE_NUMBERS,
    GOALIE_RATES,
    ORDERING_IDENTITIES,
    SKATER_COUNTS,
    SKATER_NUMBERS,
    SKATER_TIMES,
    TOTALS,
)
from .serializers import PaginationQuerySerializer, StrictDateField

SEASON_PATTERN = re.compile(r"[0-9]{8}")
MAX_SEARCH_LENGTH = 128
MAX_FILTER_LENGTH = 512
MAX_ORDERING_LENGTH = 1024


class SeasonIdField(serializers.CharField):
    def get_value(self, dictionary):
        return dictionary.get(self.field_name, serializers.empty)

    def to_internal_value(self, data):
        if not isinstance(data, str) or SEASON_PATTERN.fullmatch(data) is None:
            raise serializers.ValidationError(
                "Use a consecutive eight-digit season ID, e.g. 20262027."
            )
        try:
            return normalize_season_id(data)
        except ValueError as error:
            raise serializers.ValidationError("Use a consecutive eight-digit season ID.") from error


class CsvField(serializers.CharField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        items = [item.strip() for item in value.split(",")]
        if not all(items) or len(set(items)) != len(items):
            raise serializers.ValidationError("Use distinct, nonempty comma-separated values.")
        return items


class FiniteNumberField(serializers.FloatField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail("invalid")
        return value


class QueryBooleanField(serializers.BooleanField):
    def get_value(self, dictionary):
        return dictionary.get(self.field_name, serializers.empty)

    def to_internal_value(self, data):
        if data not in ("true", "false"):
            self.fail("invalid", input=data)
        return data == "true"


class PlayersQuerySerializer(PaginationQuerySerializer):
    season_id = SeasonIdField(
        required=False,
        help_text="Consecutive eight-digit ID. Omission selects newest loaded SBS season across both player types; no calendar fallback.",
    )
    player_type = serializers.ChoiceField(choices=[SKATER, GOALIE], default=SKATER)
    mode = serializers.ChoiceField(
        choices=[TOTALS, AVERAGES],
        default=TOTALS,
        help_text="Averages apply to skaters only; goalie rates are part of totals.",
    )
    search = serializers.CharField(
        required=False,
        max_length=MAX_SEARCH_LENGTH,
        help_text="Case-insensitive literal name substring.",
    )
    team = CsvField(
        required=False,
        max_length=MAX_FILTER_LENGTH,
        help_text="Season participation abbreviations, exact and case-sensitive; comma-separated OR. Does not select team-only contributions.",
    )
    position = CsvField(
        required=False,
        max_length=MAX_FILTER_LENGTH,
        help_text="Current profile position abbreviations; comma-separated OR.",
    )
    nation = CsvField(
        required=False,
        max_length=MAX_FILTER_LENGTH,
        help_text="Current profile nationality abbreviations; comma-separated OR.",
    )
    birth_date_min = StrictDateField(
        required=False, help_text="Inclusive date of birth, YYYY-MM-DD."
    )
    birth_date_max = StrictDateField(
        required=False, help_text="Inclusive date of birth, YYYY-MM-DD."
    )
    rookie = QueryBooleanField(
        required=False, help_text="Exact true or false; omission does not filter rookies."
    )
    ordering = serializers.CharField(
        required=False,
        max_length=MAX_ORDERING_LENGTH,
        help_text="Comma-separated allowlisted identity/statistic fields; '-' descending. Default -points,last_name,nhl_id for skaters, -wins,last_name,nhl_id for goalies. Unknown values last in either direction; ties use last_name and nhl_id.",
    )

    def get_fields(self):
        fields = super().get_fields()
        for field in sorted(ALL_NUMBERS):
            fields[field + "_isnull"] = QueryBooleanField(
                required=False,
                help_text=f"Exact true selects unknown {field}; false selects known values.",
            )
            for suffix in ("min", "max"):
                fields[field + "_" + suffix] = FiniteNumberField(
                    required=False,
                    help_text=f"Inclusive {suffix}imum for {field} in selected mode. TOI in seconds; save_percentage is a fraction. Only fields for the selected player_type are accepted.",
                )
        return fields

    def to_internal_value(self, data):
        blanks = {key: ["Supply a nonempty value."] for key in data if data[key] == ""}
        if blanks:
            raise serializers.ValidationError(blanks)
        return super().to_internal_value(data)

    def validate(self, attrs):
        player_type = attrs["player_type"]
        numbers = GOALIE_NUMBERS if player_type == GOALIE else SKATER_NUMBERS
        errors = {}
        if player_type == GOALIE and attrs["mode"] == AVERAGES:
            errors["mode"] = ["Goalies support mode=totals only."]
        for field in ALL_NUMBERS:
            low, high = attrs.get(field + "_min"), attrs.get(field + "_max")
            if field not in numbers:
                for suffix in ("min", "max", "isnull"):
                    if field + "_" + suffix in attrs:
                        errors[field + "_" + suffix] = ["Not available for this player_type."]
            elif low is not None and high is not None and low > high:
                errors[field + "_max"] = ["Maximum must be greater than or equal to minimum."]
        if "ordering" in attrs:
            terms = attrs["ordering"].split(",")
            names = [term.removeprefix("-") for term in terms]
            if any(name not in numbers | ORDERING_IDENTITIES for name in names) or len(
                set(names)
            ) != len(names):
                errors["ordering"] = [
                    "Use distinct allowlisted fields for the selected player_type."
                ]
        if (
            attrs.get("birth_date_min")
            and attrs.get("birth_date_max")
            and attrs["birth_date_min"] > attrs["birth_date_max"]
        ):
            errors["birth_date_max"] = ["Maximum must be greater than or equal to minimum."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class CatalogueTeamSerializer(serializers.Serializer):
    nhl_id = serializers.IntegerField(allow_null=True)
    abbr = serializers.CharField()
    name = serializers.CharField()
    slug = serializers.CharField(allow_null=True)


class SkaterTotalsSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[SKATER_TOTALS_KIND])
    games = serializers.IntegerField()

    def get_fields(self):
        fields = super().get_fields()
        fields.update({field: serializers.IntegerField(allow_null=True) for field in SKATER_COUNTS})
        fields.update(
            {
                field: serializers.IntegerField(
                    allow_null=True, help_text="Per-game ice time in seconds, in both modes."
                )
                for field in SKATER_TIMES
            }
        )
        return fields


class SkaterAveragesSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[SKATER_AVERAGES_KIND])
    games = serializers.IntegerField()

    def get_fields(self):
        fields = super().get_fields()
        fields.update(
            {
                field: serializers.FloatField(
                    allow_null=True, help_text="Per-game average, shared reader precision."
                )
                for field in SKATER_COUNTS
            }
        )
        fields.update(
            {
                field: serializers.IntegerField(
                    allow_null=True, help_text="Per-game ice time in seconds, in both modes."
                )
                for field in SKATER_TIMES
            }
        )
        return fields


class GoalieSeasonSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[GOALIE_TOTALS_KIND])
    games = serializers.IntegerField()

    def get_fields(self):
        fields = super().get_fields()
        fields.update({field: serializers.IntegerField(allow_null=True) for field in GOALIE_COUNTS})
        fields.update({field: serializers.FloatField(allow_null=True) for field in GOALIE_RATES})
        fields["save_percentage"].help_text = "Fraction from 0 to 1, not a percentage out of 100."
        fields[
            "goals_against_average"
        ].help_text = "Goals allowed per 60 minutes. Null when the shared reader lacks a reliable denominator."
        return fields


class CataloguePlayerSerializer(serializers.Serializer):
    player_type = serializers.ChoiceField(choices=[SKATER, GOALIE])
    nhl_id = serializers.IntegerField()
    name = serializers.CharField()
    last_name = serializers.CharField()
    slug = serializers.CharField()
    image_url = serializers.SerializerMethodField()
    nation_flag_url = serializers.SerializerMethodField()
    position_abbr = serializers.CharField()
    position_name = serializers.CharField()
    nation = serializers.CharField()
    nation_abbr = serializers.CharField()
    birth_date = serializers.DateField()
    age = serializers.IntegerField(allow_null=True)
    height_cm = serializers.IntegerField(allow_null=True)
    weight_kg = serializers.IntegerField(allow_null=True)
    weight_lb = serializers.IntegerField(allow_null=True)
    draft_year = serializers.IntegerField(allow_null=True)
    draft_number = serializers.IntegerField(allow_null=True)
    rookie = serializers.BooleanField()
    teams = CatalogueTeamSerializer(many=True)
    availability = serializers.ChoiceField(choices=["complete", "partial"])
    stats = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_image_url(self, row):
        image = row["_player"].image
        return image.url if image else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_nation_flag_url(self, row):
        flag = row["_player"].nation_flag
        return flag.url if flag else None

    @extend_schema_field(
        PolymorphicProxySerializer(
            component_name="CatalogueSeasonStatistics",
            serializers={
                SKATER_TOTALS_KIND: SkaterTotalsSerializer,
                SKATER_AVERAGES_KIND: SkaterAveragesSerializer,
                GOALIE_TOTALS_KIND: GoalieSeasonSerializer,
            },
            resource_type_field_name="kind",
        )
    )
    def get_stats(self, row):
        if row["player_type"] == GOALIE:
            serializer, kind = GoalieSeasonSerializer, GOALIE_TOTALS_KIND
        elif self.context["mode"] == AVERAGES:
            serializer, kind = SkaterAveragesSerializer, SKATER_AVERAGES_KIND
        else:
            serializer, kind = SkaterTotalsSerializer, SKATER_TOTALS_KIND
        return serializer({**row["stats"], "kind": kind}).data


class CatalogueMetaSerializer(serializers.Serializer):
    season_id = serializers.CharField(allow_null=True)
    player_type = serializers.ChoiceField(choices=[SKATER, GOALIE])
    mode = serializers.ChoiceField(choices=[TOTALS, AVERAGES])
    ordering = serializers.CharField()


class PlayersResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = CataloguePlayerSerializer(many=True)
    meta = CatalogueMetaSerializer()
