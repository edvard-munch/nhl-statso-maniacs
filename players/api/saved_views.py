"""Shared private response, CSRF body validation and schema contracts for saved lists."""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_cookie
from drf_spectacular.utils import OpenApiParameter
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from nhl_web_app.api.auth_views import json_body
from nhl_web_app.api.serializers import ErrorResponseSerializer
from .serializers import StrictQuerySerializer

SAVED_LIST_ERRORS = {
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
class PrivateSavedListView(APIView):
    permission_classes = [IsAuthenticated]
