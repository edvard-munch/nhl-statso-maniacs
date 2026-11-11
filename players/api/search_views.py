"""Public JSON search and bounded autocomplete with no viewer-specific state."""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from nhl_web_app.api.pagination import ApiPagination
from .catalogue_serializers import CsvField, MAX_FILTER_LENGTH, MAX_SEARCH_LENGTH
from .profile_views import READ_ERRORS
from .serializers import PaginationQuerySerializer, QueryIntegerField, StrictQuerySerializer
from .search import (
    ENTITY_TYPES,
    DEFAULT_SUGGESTIONS_LIMIT,
    MAX_SUGGESTIONS_LIMIT,
    SEARCH_ORDER_LABEL,
    search_queryset,
    result_data,
)


class SearchQuerySerializer(StrictQuerySerializer):
    q = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=MAX_SEARCH_LENGTH,
        help_text="Trimmed literal case-insensitive name substring; team abbreviations also match. Omitted/blank query returns no entities without database reads.",
    )
    entity_type = CsvField(
        required=False,
        default=list(ENTITY_TYPES),
        max_length=MAX_FILTER_LENGTH,
        help_text="Distinct comma-separated skater,goalie,team codes; omission searches all. The response reports the resolved canonical order.",
    )

    def to_internal_value(self, data):
        # HTML-style query parsing otherwise replaces an explicit blank with the
        # default type list before the CSV validator sees it.
        if "entity_type" in data and data["entity_type"] == "":
            raise serializers.ValidationError({"entity_type": ["Supply a nonempty value."]})
        return super().to_internal_value(data)

    def validate_entity_type(self, values):
        if any(value not in ENTITY_TYPES for value in values):
            raise serializers.ValidationError("Use skater, goalie or team.")
        return [value for value in ENTITY_TYPES if value in values]


class SearchPageQuerySerializer(SearchQuerySerializer, PaginationQuerySerializer):
    pass


class SearchSuggestionsQuerySerializer(SearchQuerySerializer):
    limit = QueryIntegerField(
        min_value=1, max_value=MAX_SUGGESTIONS_LIMIT, default=DEFAULT_SUGGESTIONS_LIMIT
    )


class SearchEntitySerializer(serializers.Serializer):
    entity_type = serializers.ChoiceField(choices=ENTITY_TYPES)
    nhl_id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField(allow_blank=True)
    image_url = serializers.CharField(allow_null=True)
    position_abbr = serializers.CharField(allow_blank=True, allow_null=True)
    abbr = serializers.CharField(allow_blank=True, allow_null=True)


class SearchMetaSerializer(serializers.Serializer):
    q = serializers.CharField(allow_blank=True)
    entity_types = serializers.ListField(child=serializers.ChoiceField(choices=ENTITY_TYPES))
    ordering = serializers.CharField()


class SearchResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SearchEntitySerializer(many=True)
    meta = SearchMetaSerializer()


class SearchSuggestionsMetaSerializer(SearchMetaSerializer):
    limit = serializers.IntegerField()
    has_more = serializers.BooleanField()


class SearchSuggestionsResponseSerializer(serializers.Serializer):
    results = SearchEntitySerializer(many=True)
    meta = SearchSuggestionsMetaSerializer()


def metadata(query):
    return {"q": query["q"], "entity_types": query["entity_type"], "ordering": SEARCH_ORDER_LABEL}


@method_decorator(never_cache, name="dispatch")
class PublicSearchView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class SearchView(PublicSearchView):
    @extend_schema(
        operation_id="search_list",
        tags=["search"],
        parameters=[SearchPageQuerySerializer],
        responses={status.HTTP_200_OK: SearchResponseSerializer, **READ_ERRORS},
        description="Public identity-only mixed skater/goalie/team search. Literal case-insensitive names plus team abbreviations; no saved-season participation requirement. Ranked exact, prefix, substring then lowercased name, typed group and NHL ID. Typed IDs remain distinct across models. Global SQL count/order/pagination, bounded queries and selected columns only. Omitted/blank q is empty with no entity reads. No HTML labels, private flags, statistics, mutations or NHL calls.",
    )
    def get(self, request):
        query = SearchPageQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        rows = search_queryset(params["q"], params["entity_type"])
        paginator = ApiPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        data = SearchEntitySerializer([result_data(row) for row in page], many=True).data
        return paginator.get_paginated_response(data, meta=metadata(params))


class SearchSuggestionsView(PublicSearchView):
    @extend_schema(
        operation_id="search_suggestions_list",
        tags=["search"],
        parameters=[SearchSuggestionsQuerySerializer],
        responses={status.HTTP_200_OK: SearchSuggestionsResponseSerializer, **READ_ERRORS},
        description="Bounded public autocomplete preview with the same typed identity DTO, matching and ranking as search. limit defaults to 10, maximum 20; one SQL query reads at most limit+1 rows, without COUNT. meta.has_more signals additional matches; use full search for pagination. No separators, full-results HTML sentinel or viewer state. Blank/omitted q returns an empty preview without entity reads.",
    )
    def get(self, request):
        query = SearchSuggestionsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        rows = list(search_queryset(params["q"], params["entity_type"])[: params["limit"] + 1])
        data = SearchEntitySerializer(
            [result_data(row) for row in rows[: params["limit"]]], many=True
        ).data
        return Response(
            {
                "results": data,
                "meta": {
                    **metadata(params),
                    "limit": params["limit"],
                    "has_more": len(rows) > params["limit"],
                },
            }
        )
