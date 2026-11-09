"""Explicit scoreboard request/response contract, independent of ORM serialization."""

import re

from rest_framework import serializers

from nhl_web_app.api.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
INTEGER_PATTERN = re.compile(r"[0-9]+")


class StrictDateField(serializers.DateField):
    def to_internal_value(self, data):
        if not isinstance(data, str) or DATE_PATTERN.fullmatch(data) is None:
            self.fail("invalid", format="YYYY-MM-DD")
        return super().to_internal_value(data)


class QueryIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if not isinstance(data, str) or INTEGER_PATTERN.fullmatch(data) is None:
            self.fail("invalid")
        return super().to_internal_value(data)


class ScoreboardQuerySerializer(serializers.Serializer):
    date = StrictDateField(
        input_formats=["iso-8601"],
        help_text="Required Pacific NHL schedule date, exactly YYYY-MM-DD; never falls back to another day.",
    )
    page = QueryIntegerField(min_value=1, default=1)
    page_size = QueryIntegerField(min_value=1, max_value=MAX_PAGE_SIZE, default=DEFAULT_PAGE_SIZE)

    def to_internal_value(self, data):
        errors = {
            name: ["Unsupported query parameter."] for name in data if name not in self.fields
        }
        for name in data:
            if hasattr(data, "getlist") and len(data.getlist(name)) != 1:
                errors[name] = ["Supply this parameter once."]
        if errors:
            raise serializers.ValidationError(errors)
        return super().to_internal_value(data)


class FreshnessSerializer(serializers.Serializer):
    has_data = serializers.BooleanField()
    is_final = serializers.BooleanField()
    saved_at = serializers.DateTimeField(allow_null=True)
    checked_at = serializers.DateTimeField()
    age_seconds = serializers.FloatField(allow_null=True)
    stale_after_seconds = serializers.IntegerField()
    is_stale = serializers.BooleanField()
    partial = serializers.BooleanField(
        help_text="Scoreboard team/score fields are unavailable or ambiguous; does not assess player-statistics completeness."
    )


class ScoreboardTeamSerializer(serializers.Serializer):
    nhl_id = serializers.IntegerField()
    name = serializers.CharField()
    abbr = serializers.CharField()
    slug = serializers.CharField()


class ScoreboardGameSerializer(serializers.Serializer):
    nhl_id = serializers.IntegerField()
    slug = serializers.CharField()
    date = serializers.DateField()
    is_final = serializers.BooleanField()
    away_team = ScoreboardTeamSerializer(allow_null=True)
    home_team = ScoreboardTeamSerializer(allow_null=True)
    away_score = serializers.IntegerField(allow_null=True)
    home_score = serializers.IntegerField(allow_null=True)
    score_outcome = serializers.ChoiceField(choices=["OT", "SO"], allow_null=True)
    score_source = serializers.ChoiceField(choices=["legacy_result"], allow_null=True)
    freshness = FreshnessSerializer()


class ScoreboardMetaSerializer(serializers.Serializer):
    date = serializers.DateField()
    freshness = FreshnessSerializer()


class ScoreboardResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ScoreboardGameSerializer(many=True)
    meta = ScoreboardMetaSerializer()
