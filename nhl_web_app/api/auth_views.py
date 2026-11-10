"""Session authentication with anonymous-login CSRF enforcement and JSON responses."""

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token, rotate_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.vary import vary_on_cookie
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import UnsupportedMediaType, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from players.api.serializers import StrictQuerySerializer
from .auth_serializers import (
    AuthResponseSerializer,
    CsrfResponseSerializer,
    LoginCredentialsSerializer,
    SessionResponseSerializer,
)
from .serializers import ErrorResponseSerializer
from .errors import InvalidCredentials

CSRF_HEADER = OpenApiParameter(
    "X-CSRFToken",
    str,
    OpenApiParameter.HEADER,
    required=True,
    description="Token returned by the CSRF bootstrap or last successful login/logout; send the corresponding same-origin cookies.",
)
AUTH_ERRORS = {
    code: ErrorResponseSerializer
    for code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_405_METHOD_NOT_ALLOWED,
        status.HTTP_406_NOT_ACCEPTABLE,
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
}


def validate_query(request):
    query = StrictQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)


def json_body(request, *, allow_empty=False):
    # Django CSRF checks can consume form streams before DRF's parser sees them.
    # Enforce the wire media type explicitly rather than accepting an empty fallback.
    content_type = request._request.content_type
    empty_untyped = not content_type and request.META.get("CONTENT_LENGTH", "0") in ("", "0")
    if content_type != "application/json" and not (allow_empty and empty_untyped):
        raise UnsupportedMediaType(content_type or "unspecified")
    return request.data


def session_data(user):
    authenticated = bool(user.is_authenticated)
    return {
        "authenticated": authenticated,
        "user": {"id": user.pk, "username": user.get_username()} if authenticated else None,
    }


@method_decorator(never_cache, name="dispatch")
@method_decorator(vary_on_cookie, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class SessionLifecycleView(APIView):
    # The dispatch decorator checks the raw Django request before DRF's exemption,
    # including anonymous requests that SessionAuthentication intentionally skips.
    permission_classes = [AllowAny]


class CsrfView(SessionLifecycleView):
    authentication_classes = []

    @extend_schema(
        operation_id="auth_csrf_retrieve",
        tags=["auth"],
        responses={status.HTTP_200_OK: CsrfResponseSerializer, **AUTH_ERRORS},
        description="Private/no-store masked CSRF bootstrap. Works with CSRF_COOKIE_HTTPONLY and CSRF_USE_SESSIONS. May establish framework CSRF/session state; never creates accounts or player data. No query parameters.",
    )
    def get(self, request):
        validate_query(request)
        return Response(CsrfResponseSerializer({"csrf_token": get_token(request._request)}).data)


class SessionView(SessionLifecycleView):
    @extend_schema(
        operation_id="auth_session_retrieve",
        tags=["auth"],
        responses={status.HTTP_200_OK: SessionResponseSerializer, **AUTH_ERRORS},
        description="Private/no-store session discovery for anonymous or authenticated callers. Anonymous/expired/inactive sessions return authenticated=false and user=null, without redirects. Only the current user's ID and username are exposed. No query parameters.",
    )
    def get(self, request):
        validate_query(request)
        return Response(SessionResponseSerializer(session_data(request.user)).data)


class LoginView(SessionLifecycleView):
    @extend_schema(
        operation_id="auth_login_create",
        tags=["auth"],
        parameters=[CSRF_HEADER],
        request=LoginCredentialsSerializer,
        responses={status.HTTP_200_OK: AuthResponseSerializer, **AUTH_ERRORS},
        description="CSRF-protected JSON login, including anonymous requests. Uses Django authentication backends and session fixation protection. Invalid/unknown/inactive credentials share a generic invalid_credentials 400 response. Success returns minimal identity and a rotated CSRF token. No redirects, next field or query parameters.",
    )
    def post(self, request):
        validate_query(request)
        credentials = LoginCredentialsSerializer(data=json_body(request))
        credentials.is_valid(raise_exception=True)
        user = authenticate(
            request._request,
            **{
                get_user_model().USERNAME_FIELD: credentials.validated_data["username"],
                "password": credentials.validated_data["password"],
            },
        )
        if user is None or not user.is_active:
            raise InvalidCredentials()
        login(request._request, user)
        request.user = user
        return Response(
            AuthResponseSerializer(
                {**session_data(user), "csrf_token": get_token(request._request)}
            ).data
        )


class LogoutView(SessionLifecycleView):
    @extend_schema(
        operation_id="auth_logout_create",
        tags=["auth"],
        parameters=[CSRF_HEADER],
        request=None,
        responses={status.HTTP_200_OK: AuthResponseSerializer, **AUTH_ERRORS},
        description="CSRF-protected logout, including anonymous callers. Accepts an empty body or empty JSON object only. Flushes the current auth session, rotates CSRF and returns anonymous identity plus a fresh token. No redirects or query parameters; repeated valid-CSRF logout remains anonymous.",
    )
    def post(self, request):
        validate_query(request)
        body = json_body(request, allow_empty=True)
        if not isinstance(body, dict) or body:
            raise ValidationError(
                {"non_field_errors": ["Supply an empty request body or JSON object."]}
            )
        logout(request._request)
        request.user = request._request.user
        rotate_token(request._request)
        return Response(
            AuthResponseSerializer(
                {**session_data(request.user), "csrf_token": get_token(request._request)}
            ).data
        )
