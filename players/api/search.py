"""Public mixed-entity identity search, ranked and paginated in PostgreSQL."""

from django.db.models import Case, CharField, IntegerField, Q, Value, When
from django.db.models.functions import Lower

from players.models import Goalie, Skater, Team
from players.season_stats import SKATER, GOALIE

TEAM = "team"
ENTITY_TYPES = (SKATER, GOALIE, TEAM)
ENTITY_MODELS = {SKATER: Skater, GOALIE: Goalie, TEAM: Team}
EXACT_RANK = 0
PREFIX_RANK = 1
SUBSTRING_RANK = 2
SEARCH_ORDERING = ("search_rank", "normalized_name", "entity_order", "nhl_id")
SEARCH_ORDER_LABEL = "relevance,name,entity_type,nhl_id"
SEARCH_COLUMNS = (
    "entity_type",
    "nhl_id",
    "name",
    "slug",
    "image",
    "position_abbr",
    "abbr",
    *SEARCH_ORDERING[:-1],
)
DEFAULT_SUGGESTIONS_LIMIT = 10
MAX_SUGGESTIONS_LIMIT = 20


def search_queryset(query, entity_types):
    parts = []
    for entity_order, entity_type in enumerate(ENTITY_TYPES):
        if entity_type not in entity_types:
            continue
        model = ENTITY_MODELS[entity_type]
        matches = Q(name__icontains=query)
        exact = Q(name__iexact=query)
        prefix = Q(name__istartswith=query)
        extra = (
            {"position_abbr": Value(None, output_field=CharField())}
            if entity_type == TEAM
            else {"abbr": Value(None, output_field=CharField())}
        )
        if entity_type == TEAM:
            matches |= Q(abbr__icontains=query)
            exact |= Q(abbr__iexact=query)
            prefix |= Q(abbr__istartswith=query)
        queryset = (
            model.objects.order_by()
            .filter(matches)
            .annotate(
                entity_type=Value(entity_type, output_field=CharField()),
                search_rank=Case(
                    When(exact, then=Value(EXACT_RANK)),
                    When(prefix, then=Value(PREFIX_RANK)),
                    default=Value(SUBSTRING_RANK),
                    output_field=IntegerField(),
                ),
                normalized_name=Lower("name"),
                entity_order=Value(entity_order, output_field=IntegerField()),
                **extra,
            )
            .values(*SEARCH_COLUMNS)
        )
        parts.append(queryset if query else queryset.none())
    return (
        parts[0].union(*parts[1:], all=True).order_by(*SEARCH_ORDERING)
        if len(parts) > 1
        else parts[0].order_by(*SEARCH_ORDERING)
    )


def result_data(row):
    field = ENTITY_MODELS[row["entity_type"]]._meta.get_field("image")
    return {
        **{
            key: row[key]
            for key in ("entity_type", "nhl_id", "name", "slug", "position_abbr", "abbr")
        },
        "image_url": field.storage.url(row["image"]) if row["image"] else None,
    }
