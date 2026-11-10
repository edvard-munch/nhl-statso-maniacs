"""Explicit saved-statistics request/response contracts, independent of ORM serialization."""

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
    def get_value(self, dictionary):
        # QueryDict's HTML handling otherwise replaces explicit blanks with defaults.
        return dictionary.get(self.field_name, serializers.empty)

    def to_internal_value(self, data):
        if not isinstance(data, str) or INTEGER_PATTERN.fullmatch(data) is None:
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictQuerySerializer(serializers.Serializer):
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


class PaginationQuerySerializer(StrictQuerySerializer):
    page = QueryIntegerField(min_value=1, default=1)
    page_size = QueryIntegerField(min_value=1, max_value=MAX_PAGE_SIZE, default=DEFAULT_PAGE_SIZE)


class ScoreboardQuerySerializer(PaginationQuerySerializer):
    date = StrictDateField(
        input_formats=["iso-8601"],
        help_text="Required Pacific NHL schedule date, exactly YYYY-MM-DD; never falls back to another day.",
    )


class SeasonSerializer(serializers.Serializer):
    season_id = serializers.CharField()
    label = serializers.CharField()


class SeasonsMetaSerializer(serializers.Serializer):
    default_season_id = serializers.CharField(
        allow_null=True,
        help_text="Newest loaded NHL regular-season SBS season across skaters and goalies; null when none exist. Independent of pagination and calendar date.",
    )


class SeasonsResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SeasonSerializer(many=True)
    meta = SeasonsMetaSerializer()


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


class GameDetailQuerySerializer(StrictQuerySerializer):
    """A detail resource accepts no list/date query parameters."""


class SkaterGameStatsSerializer(serializers.Serializer):
    goals = serializers.IntegerField(allow_null=True)
    assists = serializers.IntegerField(allow_null=True)
    points = serializers.IntegerField(allow_null=True)
    plus_minus = serializers.IntegerField(allow_null=True)
    penalty_minutes = serializers.IntegerField(allow_null=True)
    shots_on_goal = serializers.IntegerField(allow_null=True)
    hits = serializers.IntegerField(allow_null=True)
    blocked_shots = serializers.IntegerField(allow_null=True)
    faceoffs_won = serializers.IntegerField(allow_null=True)
    pp_points = serializers.IntegerField(allow_null=True)
    sh_points = serializers.IntegerField(allow_null=True)
    toi_seconds = serializers.IntegerField(allow_null=True)
    pp_toi_seconds = serializers.IntegerField(allow_null=True)
    sh_toi_seconds = serializers.IntegerField(allow_null=True)


class GoalieGameStatsSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["W", "L", "O", "OT"], allow_null=True)
    toi_seconds = serializers.IntegerField(allow_null=True)
    goals_against = serializers.IntegerField(allow_null=True)
    saves = serializers.IntegerField(allow_null=True)
    shots_against = serializers.IntegerField(allow_null=True)
    save_percentage = serializers.FloatField(
        allow_null=True, help_text="Fraction from 0 to 1, not a 0–100 percentage."
    )
    shutouts = serializers.IntegerField(allow_null=True)


class GamePlayerSerializer(serializers.Serializer):
    player_type = serializers.ChoiceField(choices=["skater", "goalie"])
    nhl_id = serializers.IntegerField()
    name = serializers.CharField()
    last_name = serializers.CharField(allow_blank=True)
    slug = serializers.CharField()
    position_abbr = serializers.CharField(
        help_text="Current saved profile metadata, not a historical reconstruction."
    )
    game_position = serializers.CharField(allow_null=True)
    sweater_number = serializers.IntegerField(allow_null=True)
    availability = serializers.ChoiceField(choices=["complete", "partial", "missing", "unverified"])


class GameSkaterSerializer(GamePlayerSerializer):
    stats = SkaterGameStatsSerializer()


class GameGoalieSerializer(GamePlayerSerializer):
    stats = GoalieGameStatsSerializer()


class GameRosterSerializer(serializers.Serializer):
    forwards = GameSkaterSerializer(many=True)
    defencemen = GameSkaterSerializer(many=True)
    goalies = GameGoalieSerializer(many=True)


class GameRostersSerializer(serializers.Serializer):
    away = GameRosterSerializer()
    home = GameRosterSerializer()


class GameDetailFreshnessSerializer(FreshnessSerializer):
    partial = serializers.BooleanField(
        help_text="Saved teams/scores, roster groups or requested player fields are incomplete/unverified; does not infer source freshness."
    )


class GameDetailSerializer(ScoreboardGameSerializer):
    date = serializers.DateField(allow_null=True)
    freshness = GameDetailFreshnessSerializer()
    rosters = GameRostersSerializer()
