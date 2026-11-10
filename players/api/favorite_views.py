"""Session-private favorite lists and CSRF-protected idempotent membership writes."""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_cookie
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nhl_web_app.api.auth_views import CSRF_HEADER, json_body
from nhl_web_app.api.pagination import ApiPagination
from nhl_web_app.api.serializers import ErrorResponseSerializer
from players.saved_actions import locked_user
from .catalogue_serializers import PlayersQuerySerializer
from .favorite_serializers import (
    FavoriteMembershipSerializer,
    FavoritePlayerSerializer,
    FavoritesResponseSerializer,
)
from .favorites import delete_membership, favorite_rows, membership_target, put_membership
from .serializers import StrictQuerySerializer

FAVORITE_ERRORS = {
    code: ErrorResponseSerializer
    for code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_405_METHOD_NOT_ALLOWED,
        status.HTTP_406_NOT_ACCEPTABLE,
        status.HTTP_409_CONFLICT,
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
}
TYPED_PATH = OpenApiParameter(
    "player_type", str, OpenApiParameter.PATH, enum=["skater", "goalie"], required=True
)


def validate_empty_mutation(request):
    query = StrictQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    body = json_body(request, allow_empty=True)
    if not isinstance(body, dict) or body:
        raise ValidationError(
            {"non_field_errors": ["Supply an empty request body or JSON object."]}
        )


@method_decorator(never_cache, name="dispatch")
@method_decorator(vary_on_cookie, name="dispatch")
class PrivateFavoritesView(APIView):
    permission_classes = [IsAuthenticated]


class FavoritesView(PrivateFavoritesView):
    @extend_schema(
        operation_id="me_favorites_list",
        tags=["favorites"],
        parameters=[PlayersQuerySerializer],
        responses={status.HTTP_200_OK: FavoritesResponseSerializer, **FAVORITE_ERRORS},
        description="Current account's saved players, one typed group, selected SBS season. Uses catalogue filters/order/pagination but retains missing, ambiguous and zero-game players unless filtered out. Missing stats are null; snapshots never substitute. Quota metadata counts both unfiltered typed groups. Reads and serialization hold the same owner-row lock used by legacy writers; no domain writes or NHL calls.",
    )
    def get(self, request):
        query = PlayersQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        with locked_user(request.user) as owner:
            rows, meta = favorite_rows(owner, query.validated_data)
            paginator = ApiPagination()
            page = paginator.paginate_queryset(rows, request, view=self)
            data = FavoritePlayerSerializer(page, many=True).data
            return paginator.get_paginated_response(data, meta=meta)


class FavoriteMembershipView(PrivateFavoritesView):
    @extend_schema(
        operation_id="me_favorite_put",
        tags=["favorites"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=None,
        responses={
            status.HTTP_200_OK: FavoriteMembershipSerializer,
            status.HTTP_201_CREATED: FavoriteMembershipSerializer,
            **FAVORITE_ERRORS,
        },
        description="Explicitly add a typed player to this account's favorites. Empty body/JSON object only; no queries. 201 on creation, 200 if already saved even at/over quota. All membership reads, shared 100-player quota checks and writes hold the owner-row lock. Excess additions return 409 favorites_quota_exceeded with no change. Requires session authentication and CSRF.",
    )
    def put(self, request, player_type, nhl_id):
        validate_empty_mutation(request)
        model = membership_target(player_type, nhl_id)
        with locked_user(request.user) as owner:
            data, created = put_membership(owner, model, player_type, nhl_id)
            serialized = FavoriteMembershipSerializer(data).data
            return Response(
                serialized, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )

    @extend_schema(
        operation_id="me_favorite_delete",
        tags=["favorites"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None, **FAVORITE_ERRORS},
        description="Explicitly remove a typed favorite from this account; 204 even if membership/player is already absent. Empty body/JSON object only, no queries. Invalid type/nonpositive/out-of-range IDs are 404. Valid removals work at/over quota and preserve comparison/other accounts. Requires session authentication and CSRF; writes hold the owner-row lock.",
    )
    def delete(self, request, player_type, nhl_id):
        validate_empty_mutation(request)
        model = membership_target(player_type, nhl_id)
        with locked_user(request.user) as owner:
            delete_membership(owner, model, player_type, nhl_id)
            return Response(status=status.HTTP_204_NO_CONTENT)
