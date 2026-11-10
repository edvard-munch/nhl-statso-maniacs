"""Session lifecycle and anonymous-login CSRF over synthetic accounts only."""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse
from django.utils import timezone
import pytest

from players.models import Goalie, LoaderRun, LoaderScheduleState, Skater, Team

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
PASSWORD = "synthetic-auth-api-password-123"


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def account():
    return get_user_model().objects.create_user(
        username="api-session-user", password=PASSWORD, email="private@example.invalid"
    )


@pytest.fixture
def browser():
    return Client(enforce_csrf_checks=True)


def url(name):
    return reverse("api_v1:auth-" + name)


def bootstrap(browser, **kwargs):
    response = browser.get(url("csrf"), **kwargs)
    assert response.status_code == 200, response.content
    return response.json()["csrf_token"]


def post(browser, route, body=None, *, token=None, **kwargs):
    if token:
        kwargs["HTTP_X_CSRFTOKEN"] = token
    return browser.post(
        url(route),
        json.dumps(body if body is not None else {}),
        content_type="application/json",
        **kwargs,
    )


def login(browser, account, **kwargs):
    token = bootstrap(browser, **kwargs)
    response = post(
        browser,
        "login",
        {"username": account.username, "password": PASSWORD},
        token=token,
        **kwargs,
    )
    assert response.status_code == 200, response.content
    return response


def assert_private_json(response):
    assert response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"] and "private" in response["Cache-Control"]
    assert "cookie" in response.get("Vary", "").lower()
    assert response["X-Request-ID"]


def test_anonymous_bootstrap_and_session_are_json_private_and_do_not_create_accounts(
    browser, django_assert_num_queries, offline
):
    with django_assert_num_queries(0):
        csrf = browser.get(url("csrf"))
        session = browser.get(url("session"))
    assert len(csrf.json()["csrf_token"]) == 64
    assert session.json() == {"authenticated": False, "user": None}
    assert_private_json(csrf)
    assert_private_json(session)
    assert not get_user_model().objects.exists() and not Session.objects.exists()
    assert not offline.called


@pytest.mark.parametrize("signed_in", [False, True])
def test_login_without_csrf_is_rejected_before_authentication(
    browser, account, signed_in, monkeypatch
):
    if signed_in:
        browser.force_login(account)

    def no_auth(*args, **kwargs):
        raise AssertionError("CSRF failure must precede credential lookup")

    monkeypatch.setattr("nhl_web_app.api.auth_views.authenticate", no_auth)
    response = post(browser, "login", {"username": account.username, "password": PASSWORD})
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"
    assert_private_json(response)
    assert browser.get(url("session")).json()["authenticated"] == signed_in


def test_login_rotates_session_and_csrf_preserves_anonymous_state_and_exposes_minimal_identity(
    browser, account, offline
):
    session = browser.session
    session["draft_ui_state"] = "kept"
    session.save()
    old_key = session.session_key
    token = bootstrap(browser)
    response = post(
        browser, "login", {"username": "  api-session-user  ", "password": PASSWORD}, token=token
    )
    assert response.status_code == 200
    assert_private_json(response)
    data = response.json()
    assert data["authenticated"] and data["user"] == {
        "id": account.pk,
        "username": account.username,
    }
    assert set(data) == {"authenticated", "user", "csrf_token"}
    assert len(data["csrf_token"]) == 64
    assert (
        browser.session.session_key != old_key
        and not Session.objects.filter(session_key=old_key).exists()
    )
    assert browser.session["draft_ui_state"] == "kept"
    assert int(browser.session["_auth_user_id"]) == account.pk
    account.refresh_from_db()
    assert account.last_login is not None
    assert browser.get(url("session")).json() == {"authenticated": True, "user": data["user"]}
    assert post(browser, "logout", token=token).status_code == 403
    assert browser.get(reverse("api_v1:root")).status_code == 200
    assert "email" not in str(data) and "password" not in str(data)
    assert not offline.called


def test_authenticated_account_switch_flushes_previous_session_private_state(browser, account):
    other = get_user_model().objects.create_user(username="other-api-user", password=PASSWORD)
    browser.force_login(account)
    session = browser.session
    session["private_ui_state"] = "old-account-only"
    session.save()
    old_key = session.session_key
    token = bootstrap(browser)
    response = post(
        browser, "login", {"username": other.username, "password": PASSWORD}, token=token
    )
    assert response.status_code == 200 and response.json()["user"]["id"] == other.pk
    assert "private_ui_state" not in browser.session
    assert browser.session.session_key != old_key
    assert not Session.objects.filter(session_key=old_key).exists()


@pytest.mark.parametrize("failure", ["wrong_password", "unknown_user", "inactive_user"])
def test_invalid_credentials_have_one_generic_response_and_preserve_auth_state(
    browser, account, failure, caplog
):
    browser.force_login(account)
    old_key = browser.session.session_key
    token = bootstrap(browser)
    account.refresh_from_db()
    old_last_login = account.last_login
    name, password = account.username, "rejected-synthetic-secret"
    if failure == "unknown_user":
        name = "missing-synthetic-account"
    elif failure == "inactive_user":
        inactive = get_user_model().objects.create_user(
            username="inactive-api-user", password=PASSWORD, is_active=False
        )
        name, password = inactive.username, PASSWORD
    response = post(browser, "login", {"username": name, "password": password}, token=token)
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_credentials",
            "message": "Unable to sign in with those credentials.",
        }
    }
    assert_private_json(response)
    assert browser.session.session_key == old_key
    assert browser.get(url("session")).json()["user"]["id"] == account.pk
    assert password not in caplog.text and password not in response.content.decode()
    account.refresh_from_db()
    assert account.last_login == old_last_login


def test_logout_flushes_auth_and_rotates_csrf_including_repeated_anonymous_logout(browser, account):
    logged_in = login(browser, account).json()
    key = browser.session.session_key
    response = post(browser, "logout", token=logged_in["csrf_token"])
    assert response.status_code == 200
    assert_private_json(response)
    data = response.json()
    assert data["authenticated"] is False and data["user"] is None
    assert not Session.objects.filter(session_key=key).exists()
    assert browser.get(reverse("api_v1:root")).status_code == 403
    assert post(browser, "logout", token=logged_in["csrf_token"]).status_code == 403
    repeated = post(browser, "logout", token=data["csrf_token"])
    assert repeated.status_code == 200 and repeated.json()["user"] is None
    assert (
        post(
            browser,
            "login",
            {"username": account.username, "password": PASSWORD},
            token=repeated.json()["csrf_token"],
        ).status_code
        == 200
    )


@pytest.mark.parametrize("signed_in", [False, True])
def test_logout_requires_csrf_for_both_session_states(browser, account, signed_in):
    if signed_in:
        browser.force_login(account)
    assert post(browser, "logout").status_code == 403
    assert browser.get(url("session")).json()["authenticated"] == signed_in


@pytest.mark.parametrize("mode", ["http_only", "session", "session_http_only"])
def test_full_lifecycle_works_with_http_only_and_session_backed_csrf(
    browser, account, settings, mode
):
    settings.CSRF_USE_SESSIONS = "session" in mode
    settings.CSRF_COOKIE_HTTPONLY = "http_only" in mode
    csrf = browser.get(url("csrf"))
    token = csrf.json()["csrf_token"]
    if settings.CSRF_USE_SESSIONS:
        assert settings.CSRF_COOKIE_NAME not in csrf.cookies
        assert "_csrftoken" in browser.session
    else:
        assert csrf.cookies[settings.CSRF_COOKIE_NAME]["httponly"]
    logged_in = post(
        browser, "login", {"username": account.username, "password": PASSWORD}, token=token
    )
    assert logged_in.status_code == 200 and browser.get(url("session")).json()["authenticated"]
    assert post(browser, "logout", token=token).status_code == 403
    logged_out = post(browser, "logout", token=logged_in.json()["csrf_token"])
    assert logged_out.status_code == 200 and not browser.get(url("session")).json()["authenticated"]
    assert (
        post(
            browser,
            "login",
            {"username": account.username, "password": PASSWORD},
            token=logged_out.json()["csrf_token"],
        ).status_code
        == 200
    )


@pytest.mark.parametrize("origin", ["https://evil.example.invalid", "null"])
def test_bad_origins_fail_even_with_valid_csrf_header(browser, account, origin):
    token = bootstrap(browser, secure=True)
    response = post(
        browser,
        "login",
        {"username": account.username, "password": PASSWORD},
        token=token,
        secure=True,
        HTTP_ORIGIN=origin,
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"
    assert not browser.get(url("session")).json()["authenticated"]


def test_same_origin_https_flow_and_secure_cookies(browser, account, settings):
    settings.CSRF_COOKIE_SECURE = True
    settings.SESSION_COOKIE_SECURE = True
    csrf = browser.get(url("csrf"), secure=True)
    assert csrf.cookies[settings.CSRF_COOKIE_NAME]["secure"]
    response = post(
        browser,
        "login",
        {"username": account.username, "password": PASSWORD},
        token=csrf.json()["csrf_token"],
        secure=True,
        HTTP_ORIGIN="https://testserver",
    )
    assert response.status_code == 200
    assert (
        response.cookies[settings.SESSION_COOKIE_NAME]["httponly"]
        and response.cookies[settings.SESSION_COOKIE_NAME]["secure"]
    )


@pytest.mark.parametrize(
    "change", ["deleted_session", "expired", "password_changed", "deactivated"]
)
def test_invalidated_or_expired_identity_becomes_anonymous_without_redirect(
    browser, account, change
):
    login(browser, account)
    if change == "deleted_session":
        Session.objects.filter(session_key=browser.session.session_key).delete()
    elif change == "expired":
        Session.objects.filter(session_key=browser.session.session_key).update(
            expire_date=timezone.now() - timedelta(seconds=1)
        )
    elif change == "password_changed":
        account.set_password("changed-synthetic-password")
        account.save()
    else:
        account.is_active = False
        account.save()
    response = browser.get(url("session"))
    assert response.status_code == 200 and response.json() == {"authenticated": False, "user": None}
    assert "Location" not in response


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"username": "x"},
        {"username": "x", "password": ""},
        {"username": 123, "password": "p"},
        {"username": "x", "password": 123},
        {"username": "x", "password": "p", "next": "https://evil.invalid"},
        [],
        None,
        False,
    ],
)
def test_invalid_login_json_is_rejected_before_credential_lookup(browser, body, monkeypatch):
    token = bootstrap(browser)

    def no_auth(*args, **kwargs):
        raise AssertionError("Invalid input must not reach the backend")

    monkeypatch.setattr("nhl_web_app.api.auth_views.authenticate", no_auth)
    response = browser.post(
        url("login"), json.dumps(body), content_type="application/json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"


@pytest.mark.parametrize("body", [{"next": "/"}, [], None, False, 0, ""])
def test_logout_rejects_nonempty_or_nonobject_json_without_logging_out(browser, account, body):
    browser.force_login(account)
    token = bootstrap(browser)
    response = browser.post(
        url("logout"), json.dumps(body), content_type="application/json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 400
    assert browser.get(url("session")).json()["user"]["id"] == account.pk


def test_empty_logout_body_is_supported(browser):
    token = bootstrap(browser)
    response = browser.post(
        url("logout"), b"", content_type="application/json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200 and response.json()["user"] is None


@pytest.mark.parametrize("route", ["login", "logout"])
def test_malformed_and_non_json_requests_return_typed_errors(browser, route):
    token = bootstrap(browser)
    malformed = browser.post(
        url(route), '{"bad":', content_type="application/json", HTTP_X_CSRFTOKEN=token
    )
    assert malformed.status_code == 400 and malformed.json()["error"]["code"] == "parse_error"
    form = browser.post(url(route), {"username": "x", "password": "secret"}, HTTP_X_CSRFTOKEN=token)
    assert form.status_code == 415 and form.json()["error"]["code"] == "unsupported_media_type"


@pytest.mark.parametrize("route", ["csrf", "session", "login", "logout"])
def test_queries_and_duplicate_parameters_are_rejected(browser, route):
    token = bootstrap(browser)
    target = url(route) + "?next=/&next=/"
    if route in ("csrf", "session"):
        response = browser.get(target)
    else:
        response = browser.post(
            target, "{}", content_type="application/json", HTTP_X_CSRFTOKEN=token
        )
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"


@pytest.mark.parametrize("route", ["csrf", "session", "login", "logout"])
def test_methods_negotiation_and_domain_records_are_unchanged(browser, account, route, offline):
    models = (Team, Skater, Goalie, LoaderRun, LoaderScheduleState)
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    token = bootstrap(browser)
    if route in ("csrf", "session"):
        head = browser.head(url(route))
        assert head.status_code == 200 and head.content == b""
        assert post(browser, route, token=token).status_code == 405
    else:
        assert browser.get(url(route)).status_code == 405
    assert browser.get(url(route), HTTP_ACCEPT="text/html").status_code == 406
    assert before == {model: list(model.objects.order_by("pk").values()) for model in models}
    assert not offline.called


def test_password_whitespace_is_preserved_and_login_supports_existing_html_sessions(
    browser, account
):
    password = "  spaced-synthetic-password  "
    account.set_password(password)
    account.save()
    token = bootstrap(browser)
    response = post(
        browser, "login", {"username": account.username, "password": password}, token=token
    )
    assert response.status_code == 200
    assert browser.get(reverse("profile")).status_code == 200
    browser.force_login(account)
    assert browser.get(url("session")).json()["user"]["id"] == account.pk


def test_schema_describes_minimal_identity_credentials_and_required_csrf_header(
    client, django_assert_num_queries
):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    for route in ("csrf", "session"):
        operation = schema["paths"]["/api/v1/auth/" + route + "/"]["get"]
        assert "200" in operation["responses"]
    for route in ("login", "logout"):
        operation = schema["paths"]["/api/v1/auth/" + route + "/"]["post"]
        header = next(item for item in operation["parameters"] if item["name"] == "X-CSRFToken")
        assert header["in"] == "header" and header["required"]
        assert {"200", "400", "403", "415"} <= operation["responses"].keys()
    assert set(schema["components"]["schemas"]["SessionUser"]["properties"]) == {"id", "username"}
    assert schema["components"]["schemas"]["LoginCredentialsRequest"]["properties"]["password"][
        "writeOnly"
    ]


def test_username_normalization_matches_the_existing_django_login_form(browser, account):
    token = bootstrap(browser)
    response = post(
        browser, "login", {"username": "ａｐｉ-session-user", "password": PASSWORD}, token=token
    )
    assert response.status_code == 200 and response.json()["user"]["id"] == account.pk


def test_get_logout_and_bad_csrf_leave_authenticated_session_intact(browser, account):
    logged_in = login(browser, account).json()
    key = browser.session.session_key
    assert browser.get(url("logout")).status_code == 405
    assert post(browser, "logout", token="invalid").status_code == 403
    assert browser.session.session_key == key
    assert browser.get(url("session")).json()["user"]["id"] == account.pk
    assert post(browser, "logout", token=logged_in["csrf_token"]).status_code == 200


def test_empty_untyped_logout_body_is_supported(browser):
    token = bootstrap(browser)
    response = browser.post(url("logout"), b"", content_type="", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200


def test_bootstrap_with_session_csrf_only_creates_framework_state_and_not_accounts(
    browser, settings
):
    settings.CSRF_USE_SESSIONS = True
    response = browser.get(url("csrf"))
    assert response.status_code == 200 and browser.session.get("_csrftoken")
    assert Session.objects.count() == 1 and get_user_model().objects.count() == 0


def test_logout_preserves_another_clients_session_and_all_owned_memberships(browser, account):
    other = Client(enforce_csrf_checks=True)
    own = login(browser, account).json()
    login(other, account)
    player = Skater.objects.create(nhl_id=1, name="Owned", birth_date="2000-01-01", games=0)
    account.favorite_skaters.add(player)
    assert post(browser, "logout", token=own["csrf_token"]).status_code == 200
    assert other.get(url("session")).json()["user"]["id"] == account.pk
    assert account.favorite_skaters.filter(pk=player.pk).exists()


def test_json_with_charset_parameter_is_supported_for_login_and_logout(browser, account):
    token = bootstrap(browser)
    response = browser.post(
        url("login"),
        json.dumps({"username": account.username, "password": PASSWORD}),
        content_type="application/json; charset=utf-8",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    response = browser.post(
        url("logout"),
        "{}",
        content_type="application/json; charset=utf-8",
        HTTP_X_CSRFTOKEN=response.json()["csrf_token"],
    )
    assert response.status_code == 200
