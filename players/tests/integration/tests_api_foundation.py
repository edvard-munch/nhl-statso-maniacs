"""JSON-only API boundary without migrating legacy pages or fetching NHL data."""

from io import StringIO
import json
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.core.management import call_command
from django.http import Http404, HttpResponse
from django.test import Client
from django.urls import include, path, reverse
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.validation import validate_schema
import pytest
from rest_framework import exceptions, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from nhl_web_app.api import PREFIX
from nhl_web_app.api.views import NotFoundView
from nhl_web_app.logging_config import JsonFormatter
from players.models import LoaderRun, LoaderScheduleState

pytestmark = pytest.mark.integration


class InputSerializer(serializers.Serializer):
    season_id = serializers.RegexField(r"^\d{8}$")


class ProtectedWrite(APIView):
    def post(self, request):
        serializer = InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class PublicRead(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"public": True})


class RaisedError(APIView):
    permission_classes = [AllowAny]

    def get(self, request, error):
        errors = {
            "forbidden": exceptions.PermissionDenied("private permission detail"),
            "not_found": Http404("private resource detail"),
            "throttle": exceptions.Throttled(wait=12),
            "unexpected": RuntimeError("sensitive internals"),
            "api_server": exceptions.APIException("sensitive API internals"),
            "bad_request": BadRequest("private bad request"),
            "suspicious": SuspiciousOperation("sensitive security detail"),
            "django_permission": PermissionDenied("sensitive permission detail"),
        }
        raise errors[error]


@csrf_protect
def django_write(request):
    return HttpResponse("accepted")


def raw_error(request):
    response = HttpResponse("<h1>sensitive body</h1>", status=429)
    response["Retry-After"] = "12"
    response["Content-Length"] = "999"
    response["ETag"] = "old-representation"
    response["X-Frame-Options"] = "DENY"
    response.set_cookie("fixture", "value")
    return response


urlpatterns = [
    path("api/v1/protected/", ProtectedWrite.as_view()),
    path("api/v1/public/", PublicRead.as_view()),
    path("api/v1/errors/<str:error>/", RaisedError.as_view()),
    path("api/v1/django-write/", django_write),
    path("api/v1/raw/", raw_error),
    path("api/v1/", include("nhl_web_app.api.urls")),
    path("api/v1", NotFoundView.as_view()),
    path("legacy/write/", django_write),
    path("legacy/error/", raw_error),
]


@pytest.fixture(autouse=True)
def no_upstream(requests_mock):
    return requests_mock


@pytest.fixture
def test_routes(settings):
    settings.ROOT_URLCONF = __name__


@pytest.fixture
def signed_in(db):
    user = get_user_model().objects.create_user(username="api-foundation-user")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    return client


def csrf_post(client, path, data, **extra):
    from django.middleware.csrf import _get_new_csrf_string

    token = _get_new_csrf_string()
    client.cookies["csrftoken"] = token
    return client.post(path, data, content_type="application/json", HTTP_X_CSRFTOKEN=token, **extra)


def assert_error(response, status, code):
    assert response.status_code == status
    assert response["Content-Type"].split(";")[0] == "application/json"
    assert response.json()["error"]["code"] == code
    assert UUID(response["X-Request-ID"])
    assert "no-store" in response["Cache-Control"]
    return response.json()["error"]


def test_schema_is_public_json_valid_and_read_only(
    client, django_assert_num_queries, no_upstream, db
):
    with django_assert_num_queries(0):
        response = client.get(reverse("api_v1:schema"))
    assert response.status_code == 200 and response["Content-Type"] == "application/json"
    schema = response.json()
    validate_schema(schema)
    assert schema["openapi"] == "3.0.3"
    assert set(schema["paths"]) == {
        PREFIX,
        PREFIX + "auth/register/",
        PREFIX + "auth/csrf/",
        PREFIX + "auth/session/",
        PREFIX + "auth/login/",
        PREFIX + "auth/logout/",
        PREFIX + "seasons/",
        PREFIX + "players/",
        PREFIX + "players/{player_type}/{nhl_id}/",
        PREFIX + "players/{player_type}/{nhl_id}/seasons/",
        PREFIX + "players/{player_type}/{nhl_id}/gamelog/",
        PREFIX + "teams/",
        PREFIX + "teams/{nhl_id}/",
        PREFIX + "teams/{nhl_id}/players/",
        PREFIX + "games/",
        PREFIX + "games/{nhl_id}/",
    }
    root = schema["paths"][PREFIX]["get"]
    assert root["security"] == [{"cookieAuth": []}]
    assert root["responses"]["403"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )
    assert schema["components"]["securitySchemes"]["cookieAuth"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "sessionid",
    }
    assert not no_upstream.called


def test_schema_cli_validates_without_database_or_network(
    django_assert_num_queries, no_upstream, db
):
    output = StringIO()
    with django_assert_num_queries(0):
        call_command(
            "spectacular", "--format", "openapi-json", "--validate", "--fail-on-warn", stdout=output
        )
    schema = json.loads(output.getvalue())
    assert set(schema["paths"]) == {
        PREFIX,
        PREFIX + "auth/register/",
        PREFIX + "auth/csrf/",
        PREFIX + "auth/session/",
        PREFIX + "auth/login/",
        PREFIX + "auth/logout/",
        PREFIX + "seasons/",
        PREFIX + "players/",
        PREFIX + "players/{player_type}/{nhl_id}/",
        PREFIX + "players/{player_type}/{nhl_id}/seasons/",
        PREFIX + "players/{player_type}/{nhl_id}/gamelog/",
        PREFIX + "teams/",
        PREFIX + "teams/{nhl_id}/",
        PREFIX + "teams/{nhl_id}/players/",
        PREFIX + "games/",
        PREFIX + "games/{nhl_id}/",
    }
    assert not no_upstream.called


def test_root_defaults_to_session_auth_and_private_permissions(client):
    detail = assert_error(client.get(reverse("api_v1:root")), 403, "authentication_required")
    assert detail["message"] == "Sign in required."
    response = client.get(reverse("api_v1:root"), HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz")
    assert_error(response, 403, "authentication_required")


def test_authenticated_root_has_no_business_writes(signed_in, no_upstream):
    from players.models import Game, Skater, Goalie

    models = (Game, Skater, Goalie, LoaderRun, LoaderScheduleState)
    before = {model: list(model.objects.values()) for model in models}
    response = signed_in.get(reverse("api_v1:root"))
    assert response.status_code == 200 and response.json() == {"version": "v1"}
    assert "private" in response["Cache-Control"]
    assert {model: list(model.objects.values()) for model in models} == before
    assert not no_upstream.called


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("url", ["/api/v1/missing/", "/api/v1/schema", "/api/v1"])
def test_bad_api_routes_are_json_without_redirects(client, settings, debug, url):
    settings.DEBUG = debug
    for method in ("get", "post"):
        response = getattr(client, method)(url)
        assert_error(response, 404, "not_found")
        assert "Location" not in response


def test_head_and_options_do_not_render_html(client, signed_in):
    response = client.head(reverse("api_v1:root"))
    assert response.status_code == 403 and response.content == b""
    assert response["Content-Type"] == "application/json"
    response = signed_in.options(reverse("api_v1:root"))
    assert response.status_code == 200 and response["Content-Type"] == "application/json"


def test_accept_negotiation_and_unsupported_methods_are_json(client):
    assert_error(
        client.get(reverse("api_v1:schema"), HTTP_ACCEPT="text/html"), 406, "not_acceptable"
    )
    response = client.post(reverse("api_v1:schema"))
    assert_error(response, 405, "method_not_allowed")
    assert "GET" in response["Allow"]


def test_session_csrf_is_distinct_from_missing_auth(signed_in, test_routes):
    assert_error(
        signed_in.post("/api/v1/protected/", "{}", content_type="application/json"),
        403,
        "csrf_failed",
    )
    response = csrf_post(signed_in, "/api/v1/protected/", {"season_id": "20262027"})
    assert response.status_code == 200 and response.json() == {"season_id": "20262027"}


def test_untrusted_origin_is_csrf_failure(signed_in, test_routes):
    response = csrf_post(
        signed_in,
        "/api/v1/protected/",
        {"season_id": "20262027"},
        HTTP_ORIGIN="https://untrusted.invalid",
    )
    assert_error(response, 403, "csrf_failed")


def test_validation_json_parsing_and_media_type_errors(signed_in, test_routes):
    response = csrf_post(signed_in, "/api/v1/protected/", {"season_id": "bad"})
    detail = assert_error(response, 400, "invalid_parameters")
    assert set(detail["fields"]) == {"season_id"}
    response = csrf_post(signed_in, "/api/v1/protected/", "{bad")
    assert_error(response, 400, "parse_error")
    from django.middleware.csrf import _get_new_csrf_string

    token = _get_new_csrf_string()
    signed_in.cookies["csrftoken"] = token
    response = signed_in.post(
        "/api/v1/protected/", "body", content_type="text/plain", HTTP_X_CSRFTOKEN=token
    )
    assert_error(response, 415, "unsupported_media_type")


@pytest.mark.parametrize(
    "error,status,code",
    [
        ("forbidden", 403, "permission_denied"),
        ("not_found", 404, "not_found"),
        ("throttle", 429, "throttled"),
        ("unexpected", 500, "server_error"),
        ("api_server", 500, "server_error"),
        ("bad_request", 400, "invalid_request"),
        ("suspicious", 400, "invalid_request"),
        ("django_permission", 403, "permission_denied"),
    ],
)
@pytest.mark.parametrize("debug", [False, True])
def test_drf_and_django_errors_do_not_expose_details(
    client, settings, test_routes, error, status, code, debug
):
    settings.DEBUG = debug
    response = client.get("/api/v1/errors/" + error + "/")
    assert_error(response, status, code)
    assert b"sensitive" not in response.content and b"private" not in response.content
    assert b"<html" not in response.content and b"Traceback" not in response.content
    if status == 429:
        assert response["Retry-After"] == "12"


def test_django_csrf_handler_is_api_scoped(test_routes):
    client = Client(enforce_csrf_checks=True)
    assert_error(client.post("/api/v1/django-write/"), 403, "csrf_failed")
    response = client.post("/legacy/write/")
    assert response.status_code == 403 and response["Content-Type"].startswith("text/html")
    assert "X-Request-ID" not in response


def test_raw_middleware_error_keeps_safe_headers_but_not_old_representation(client, test_routes):
    response = client.get("/api/v1/raw/")
    assert_error(response, 429, "throttled")
    assert response["Retry-After"] == "12" and response["X-Frame-Options"] == "DENY"
    assert response.cookies["fixture"].value == "value"
    assert "ETag" not in response and "999" != response.get("Content-Length")
    response = client.get("/legacy/error/")
    assert (
        response.content == b"<h1>sensitive body</h1>" and response["ETag"] == "old-representation"
    )


def test_request_id_is_generated_not_trusted_and_correlates_server_failure(
    client, test_routes, caplog
):
    import logging

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(handler)
    try:
        response = client.get(
            "/api/v1/errors/unexpected/", HTTP_X_REQUEST_ID="untrusted-request-id"
        )
    finally:
        logging.getLogger().removeHandler(handler)
    identifier = response["X-Request-ID"]
    assert UUID(identifier)
    records = [
        record for record in caplog.records if record.getMessage() == "Unhandled API exception"
    ]
    assert len(records) == 1
    assert records[0].exc_info[0] is RuntimeError
    logged = [json.loads(line) for line in stream.getvalue().splitlines()]
    diagnostic = next(row for row in logged if row.get("message") == "Unhandled API exception")
    assert diagnostic["request_id"] == identifier
    assert diagnostic["level"] == "ERROR"
    assert "sensitive internals" in diagnostic["traceback"]


def test_production_legacy_pages_and_404s_keep_html(client, settings):
    settings.DEBUG = False
    assert client.get("/about/")["Content-Type"].startswith("text/html")
    assert client.get("/not-a-page/")["Content-Type"].startswith("text/html")
    assert client.get("/api/v10/missing/")["Content-Type"].startswith("text/html")


@pytest.mark.parametrize("use_sessions", [False, True])
def test_session_csrf_works_with_http_only_or_session_backed_tokens(
    signed_in, test_routes, settings, use_sessions
):
    from django.middleware.csrf import _get_new_csrf_string, CSRF_SESSION_KEY

    settings.CSRF_USE_SESSIONS = use_sessions
    settings.CSRF_COOKIE_HTTPONLY = True
    token = _get_new_csrf_string()
    if use_sessions:
        session = signed_in.session
        session[CSRF_SESSION_KEY] = token
        session.save()
    else:
        signed_in.cookies[settings.CSRF_COOKIE_NAME] = token
    response = signed_in.post(
        "/api/v1/protected/",
        {"season_id": "20262027"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200


class EarlyFailureMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raise SuspiciousOperation("sensitive middleware internals")


@pytest.mark.parametrize("debug", [False, True])
def test_errors_before_view_are_normalized_without_html_or_secret(client, settings, debug):
    settings.DEBUG = debug
    settings.MIDDLEWARE = [
        settings.MIDDLEWARE[0],
        __name__ + ".EarlyFailureMiddleware",
        *settings.MIDDLEWARE[1:],
    ]
    response = client.get("/api/v1/")
    assert_error(response, 400, "invalid_request")
    assert b"sensitive" not in response.content
