"""Registration parity, CSRF, atomic persistence and concurrent username policy."""

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event

from django.contrib.auth import get_user_model
from django.db import connection, connections, IntegrityError
from django.test import Client
from django.urls import reverse
import pytest

from users.forms import UserRegisterForm
from users.models import Profile
from users.registration import create_registered_user
from players.models import Skater, Team, LoaderRun, LoaderScheduleState

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
PASSWORD = "synthetic-registration-api-password-583"


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def browser():
    return Client(enforce_csrf_checks=True)


def payload(**changes):
    return {
        "username": "new-api-user",
        "email": "new@example.invalid",
        "password1": PASSWORD,
        "password2": PASSWORD,
        **changes,
    }


def token(browser):
    response = browser.get(reverse("api_v1:auth-csrf"))
    assert response.status_code == 200
    return response.json()["csrf_token"]


def register(browser, body=None, *, csrf=None, **kwargs):
    return browser.post(
        reverse("api_v1:auth-register"),
        json.dumps(payload() if body is None else body),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf or token(browser),
        **kwargs,
    )


def counts():
    return get_user_model().objects.count(), Profile.objects.count()


def test_registration_creates_hashed_user_and_default_profile_then_requires_login(
    browser, offline, mailoutbox
):
    csrf = token(browser)
    response = register(browser, csrf=csrf)
    assert response.status_code == 201 and response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"] and "private" in response["Cache-Control"]
    assert "cookie" in response["Vary"].lower() and response["X-Request-ID"]
    user = get_user_model().objects.get()
    assert response.json() == {
        "user": {"id": user.pk, "username": "new-api-user"},
        "login_required": True,
    }
    assert user.check_password(PASSWORD) and user.password != PASSWORD
    assert user.email == "new@example.invalid" and user.is_active
    assert not user.is_staff and not user.is_superuser and user.last_login is None
    assert counts() == (1, 1)
    assert user.profile.measurements_format == "USA" and user.profile.image.name == "default.jpg"
    assert browser.get(reverse("api_v1:auth-session")).json() == {
        "authenticated": False,
        "user": None,
    }
    logged_in = browser.post(
        reverse("api_v1:auth-login"),
        json.dumps({"username": user.username, "password": PASSWORD}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert logged_in.status_code == 200 and logged_in.json()["user"]["id"] == user.pk
    assert (
        PASSWORD not in response.content.decode() and user.password not in response.content.decode()
    )
    assert not offline.called and not mailoutbox


def test_username_and_email_normalization_and_password_whitespace_match_form(browser):
    password = "  synthetic-registration-spaces-583  "
    response = register(
        browser,
        payload(
            username="  ｎｅｗ-api-user  ",
            email=" Address@EXAMPLE.INVALID ",
            password1=password,
            password2=password,
        ),
    )
    assert response.status_code == 201, response.content
    user = get_user_model().objects.get()
    assert user.username == "new-api-user" and user.email == "Address@example.invalid"
    assert user.check_password(password) and not user.check_password(password.strip())


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"username": ""}, "username"),
        ({"username": "bad name!"}, "username"),
        ({"username": "x" * 151}, "username"),
        ({"email": "not-an-email"}, "email"),
        ({"email": ""}, "email"),
        ({"email": "x" * 250 + "@example.invalid"}, "email"),
        ({"password2": "does-not-match"}, "password2"),
        ({"password1": "short", "password2": "short"}, "password2"),
        ({"password1": "password123", "password2": "password123"}, "password2"),
        ({"password1": "1234567891011", "password2": "1234567891011"}, "password2"),
        ({"password1": "new-api-user", "password2": "new-api-user"}, "password2"),
    ],
)
def test_existing_form_validation_is_preserved_without_partial_creation(browser, changes, field):
    body = payload(**changes)
    form = UserRegisterForm(body)
    assert not form.is_valid() and field in form.errors
    expected = [message for error in form.errors.as_data()[field] for message in error.messages]
    response = register(browser, body)
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"
    assert response.json()["error"]["fields"][field] == expected
    assert counts() == (0, 0)


@pytest.mark.parametrize("name", ["new-api-user", "NEW-API-USER", "ｎｅｗ-api-user"])
def test_duplicate_case_and_normalized_usernames_are_field_errors(browser, name):
    existing = get_user_model().objects.create_user(username="new-api-user", password=PASSWORD)
    response = register(browser, payload(username=name))
    assert response.status_code == 400 and "username" in response.json()["error"]["fields"]
    assert counts() == (1, 1)
    existing.refresh_from_db()
    assert existing.check_password(PASSWORD)


def test_email_is_required_but_not_made_unique_by_the_api(browser):
    get_user_model().objects.create_user(username="existing", email="new@example.invalid")
    assert register(browser).status_code == 201
    assert counts() == (2, 2)


@pytest.mark.parametrize("missing", ["username", "email", "password1", "password2"])
def test_missing_required_fields_are_typed_errors(browser, missing):
    body = payload()
    body.pop(missing)
    response = register(browser, body)
    assert response.status_code == 400 and missing in response.json()["error"]["fields"]
    assert counts() == (0, 0)


@pytest.mark.parametrize(
    "field,value", [("username", 123), ("email", False), ("password1", 123), ("password2", None)]
)
def test_json_fields_are_strings_and_do_not_coerce_credentials(browser, field, value):
    response = register(browser, payload(**{field: value}))
    assert response.status_code == 400 and field in response.json()["error"]["fields"]
    assert counts() == (0, 0)


@pytest.mark.parametrize(
    "extra",
    ["is_staff", "is_superuser", "is_active", "password", "image", "measurements_format", "next"],
)
def test_unknown_and_privilege_fields_are_rejected_before_saving(browser, extra):
    response = register(browser, payload(**{extra: True}))
    assert response.status_code == 400 and extra in response.json()["error"]["fields"]
    assert counts() == (0, 0)


def test_csrf_is_required_before_any_registration_work(
    browser, monkeypatch, django_assert_num_queries
):
    def no_create(*args, **kwargs):
        raise AssertionError("Missing CSRF must precede account creation")

    monkeypatch.setattr("nhl_web_app.api.registration.create_registered_user", no_create)
    with django_assert_num_queries(0):
        response = browser.post(
            reverse("api_v1:auth-register"), json.dumps(payload()), content_type="application/json"
        )
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"
    assert counts() == (0, 0)


@pytest.mark.parametrize("mode", ["http_only", "session"])
def test_registration_and_followup_login_support_csrf_storage_modes(browser, settings, mode):
    settings.CSRF_COOKIE_HTTPONLY = mode == "http_only"
    settings.CSRF_USE_SESSIONS = mode == "session"
    csrf = token(browser)
    assert register(browser, csrf=csrf).status_code == 201
    assert not browser.get(reverse("api_v1:auth-session")).json()["authenticated"]
    response = browser.post(
        reverse("api_v1:auth-login"),
        json.dumps({"username": "new-api-user", "password": PASSWORD}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200


def test_signed_in_registration_preserves_current_session_and_owned_state(browser):
    current = get_user_model().objects.create_user(username="signed-in", password=PASSWORD)
    browser.force_login(current)
    session = browser.session
    session["private_state"] = "preserved"
    session.save()
    old_key = session.session_key
    player = Skater.objects.create(nhl_id=1, name="Owned", birth_date="2000-01-01", games=0)
    current.favorite_skaters.add(player)
    response = register(browser)
    assert response.status_code == 201 and response.json()["user"]["id"] != current.pk
    assert (
        browser.session.session_key == old_key and browser.session["private_state"] == "preserved"
    )
    assert browser.get(reverse("api_v1:auth-session")).json()["user"]["id"] == current.pk
    assert current.favorite_skaters.filter(pk=player.pk).exists()


def test_failed_registration_keeps_existing_session_and_domain_records(browser):
    current = get_user_model().objects.create_user(username="signed-in", password=PASSWORD)
    browser.force_login(current)
    key = browser.session.session_key
    models = (Skater, Team, LoaderRun, LoaderScheduleState)
    before = {model: list(model.objects.values()) for model in models}
    response = register(browser, payload(password2="mismatch"))
    assert response.status_code == 400
    assert counts() == (1, 1) and browser.session.session_key == key
    assert before == {model: list(model.objects.values()) for model in models}


def test_profile_creation_failure_rolls_back_user_and_returns_generic_error(
    browser, monkeypatch, caplog
):
    browser.raise_request_exception = False

    def fail(*args, **kwargs):
        raise IntegrityError("synthetic profile failure")

    monkeypatch.setattr(Profile.objects, "create", fail)
    response = register(browser)
    assert response.status_code == 500 and response.json()["error"]["code"] == "server_error"
    assert counts() == (0, 0)
    assert PASSWORD not in response.content.decode() and PASSWORD not in caplog.text


@pytest.mark.parametrize("origin", ["https://foreign.invalid", "null"])
def test_foreign_origin_is_rejected_even_with_a_token(browser, origin):
    csrf = token(browser)
    response = register(browser, csrf=csrf, secure=True, HTTP_ORIGIN=origin)
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"
    assert counts() == (0, 0)


def test_json_media_types_and_methods_are_explicit(browser):
    csrf = token(browser)
    form = browser.post(reverse("api_v1:auth-register"), payload(), HTTP_X_CSRFTOKEN=csrf)
    assert form.status_code == 415 and counts() == (0, 0)
    malformed = browser.post(
        reverse("api_v1:auth-register"),
        '{"bad":',
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert malformed.status_code == 400 and malformed.json()["error"]["code"] == "parse_error"
    assert browser.get(reverse("api_v1:auth-register")).status_code == 405
    assert browser.get(reverse("api_v1:auth-register"), HTTP_ACCEPT="text/html").status_code == 406
    good = browser.post(
        reverse("api_v1:auth-register"),
        json.dumps(payload()),
        content_type="application/json; charset=utf-8",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert good.status_code == 201


@pytest.mark.parametrize("body", [[], None, False])
def test_nonobject_json_cannot_create_accounts(browser, body):
    response = browser.post(
        reverse("api_v1:auth-register"),
        json.dumps(body),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token(browser),
    )
    assert response.status_code == 400 and counts() == (0, 0)


def test_queries_and_duplicates_are_rejected_without_creating_accounts(browser):
    csrf = token(browser)
    response = browser.post(
        reverse("api_v1:auth-register") + "?next=/&next=/",
        json.dumps(payload()),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400 and counts() == (0, 0)


def test_registration_schema_describes_required_fields_and_csrf_without_secrets(
    client, django_assert_num_queries
):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    operation = schema["paths"]["/api/v1/auth/register/"]["post"]
    assert operation["operationId"] == "auth_register_create" and "201" in operation["responses"]
    assert next(item for item in operation["parameters"] if item["name"] == "X-CSRFToken")[
        "required"
    ]
    body = schema["components"]["schemas"]["RegistrationCredentialsRequest"]
    assert set(body["required"]) == {"username", "email", "password1", "password2"}
    assert (
        body["properties"]["password1"]["writeOnly"]
        and body["properties"]["password2"]["writeOnly"]
    )
    assert body["properties"]["email"]["format"] == "email"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("first_flow", ["api", "html"])
def test_case_variant_api_and_html_registrations_share_the_same_transaction_lock(
    monkeypatch, first_flow
):
    first_in_save, release_first = Event(), Event()
    second_attempted, second_acquired = Event(), Event()
    original_save = UserRegisterForm.save

    def slow_first_save(form, *args, **kwargs):
        if form.cleaned_data["username"] == "CaseRace":
            first_in_save.set()
            assert release_first.wait(15), "First registration was not released"
        return original_save(form, *args, **kwargs)

    monkeypatch.setattr(UserRegisterForm, "save", slow_first_save)

    def worker(flow, name, watch=False):
        connections.close_all()
        try:
            client = Client(enforce_csrf_checks=True)
            csrf = token(client)

            def observe_lock(execute, sql, params, many, context):
                if "pg_advisory_xact_lock" in sql:
                    second_attempted.set()
                    result = execute(sql, params, many, context)
                    second_acquired.set()
                    return result
                return execute(sql, params, many, context)

            def submit():
                if flow == "api":
                    response = register(client, payload(username=name), csrf=csrf)
                else:
                    response = client.post(
                        reverse("register"), payload(username=name), HTTP_X_CSRFTOKEN=csrf
                    )
                return response.status_code

            if watch:
                with connection.execute_wrapper(observe_lock):
                    return submit()
            return submit()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker, first_flow, "CaseRace")
        try:
            assert first_in_save.wait(15), "First registration did not reach save"
            second_flow = "html" if first_flow == "api" else "api"
            second = pool.submit(worker, second_flow, "caserace", True)
            assert second_attempted.wait(15), "Second registration did not request its lock"
            assert not second_acquired.wait(0.2), (
                "Case variants must wait for the first transaction"
            )
        finally:
            release_first.set()
        assert first.result(timeout=15) == (201 if first_flow == "api" else 302)
        assert second.result(timeout=15) == (200 if second_flow == "html" else 400)
    assert counts() == (1, 1)
    assert get_user_model().objects.get().username == "CaseRace"


@pytest.mark.django_db(transaction=True)
def test_external_exact_username_race_is_a_field_error_after_database_rollback(
    browser, monkeypatch
):
    original_save = UserRegisterForm.save

    def racing_save(form, *args, **kwargs):
        def external_create():
            connections.close_all()
            try:
                get_user_model().objects.create_user(
                    username=form.cleaned_data["username"], password=PASSWORD
                )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(external_create).result(timeout=15)
        return original_save(form, *args, **kwargs)

    monkeypatch.setattr(UserRegisterForm, "save", racing_save)
    response = register(browser)
    assert response.status_code == 400 and "username" in response.json()["error"]["fields"]
    assert counts() == (1, 1)
    assert not browser.get(reverse("api_v1:auth-session")).json()["authenticated"]
