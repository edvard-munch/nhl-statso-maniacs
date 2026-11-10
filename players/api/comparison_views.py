"""Session-private comparison reads and explicit CSRF-protected mutations."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from nhl_web_app.api.auth_views import CSRF_HEADER
from nhl_web_app.api.pagination import ApiPagination
from players.saved_actions import locked_user
from .comparison import comparison_rows, put_membership, delete_membership, clear_memberships
from .comparison_serializers import (
    ComparisonQuerySerializer,
    ComparisonPlayerSerializer,
    ComparisonResponseSerializer,
    ComparisonMembershipSerializer,
)
from .profiles import player_model
from .saved_lists import membership_target
from .saved_views import (
    PrivateSavedListView,
    SAVED_LIST_ERRORS,
    TYPED_PATH,
    validate_empty_mutation,
)


class ComparisonView(PrivateSavedListView):
    @extend_schema(
        operation_id="me_comparison_list",
        tags=["comparison"],
        parameters=[ComparisonQuerySerializer],
        responses={status.HTTP_200_OK: ComparisonResponseSerializer, **SAVED_LIST_ERRORS},
        description="Current account's comparison group. Defaults to selected SBS season; scope=career uses saved career packets and rejects season_id/team. Catalogue filters/order/pagination apply. Missing/unverified/zero-game members remain unless filtered. No snapshot fallback. Quotas count both unfiltered groups with independent five-player limits. Reads/serialization hold the legacy owner lock; no domain writes or NHL calls.",
    )
    def get(self, request):
        query = ComparisonQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        with locked_user(request.user) as owner:
            rows, meta = comparison_rows(owner, query.validated_data)
            paginator = ApiPagination()
            page = paginator.paginate_queryset(rows, request, view=self)
            data = ComparisonPlayerSerializer(page, many=True).data
            return paginator.get_paginated_response(data, meta=meta)


class ComparisonMembershipView(PrivateSavedListView):
    @extend_schema(
        operation_id="me_comparison_put",
        tags=["comparison"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=None,
        responses={
            status.HTTP_200_OK: ComparisonMembershipSerializer,
            status.HTTP_201_CREATED: ComparisonMembershipSerializer,
            **SAVED_LIST_ERRORS,
        },
        description="Explicitly add a typed comparison player: 201 created, 200 already present even at/over quota. Empty body/JSON object only, no queries. Owner-locked five-player quota per type; excess new additions return 409 comparison_quota_exceeded. Requires session and CSRF.",
    )
    def put(self, request, player_type, nhl_id):
        validate_empty_mutation(request)
        model = membership_target(player_type, nhl_id)
        with locked_user(request.user) as owner:
            data, created = put_membership(owner, model, player_type, nhl_id)
            serialized = ComparisonMembershipSerializer(data).data
            return Response(
                serialized, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )

    @extend_schema(
        operation_id="me_comparison_delete",
        tags=["comparison"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None, **SAVED_LIST_ERRORS},
        description="Explicitly remove a typed comparison membership, 204 even if player/membership is absent. Invalid type/range returns 404. Empty body/JSON object only, no queries. Requires session and CSRF; owner-locked and preserves favorites, opposite type and other accounts.",
    )
    def delete(self, request, player_type, nhl_id):
        validate_empty_mutation(request)
        model = membership_target(player_type, nhl_id)
        with locked_user(request.user) as owner:
            delete_membership(owner, model, player_type, nhl_id)
            return Response(status=status.HTTP_204_NO_CONTENT)


class ComparisonGroupView(PrivateSavedListView):
    @extend_schema(
        operation_id="me_comparison_clear",
        tags=["comparison"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None, **SAVED_LIST_ERRORS},
        description="Clear only this account's typed comparison group, 204 including already empty. Invalid type returns 404. Empty body/JSON object only, no queries. Requires session and CSRF; shares owner lock with legacy writers/resets. Favorites, opposite type and other accounts are preserved.",
    )
    def delete(self, request, player_type):
        validate_empty_mutation(request)
        player_model(player_type)
        with locked_user(request.user) as owner:
            clear_memberships(owner, player_type)
            return Response(status=status.HTTP_204_NO_CONTENT)
