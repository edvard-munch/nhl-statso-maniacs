"""Current-account partial settings, HTML parity, atomicity and username races."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db import connection, connections
from django.test import Client
from django.urls import reverse
import pytest

from users.models import Profile
from players.tests.integration.tests_favorites_api_db import concurrent_changes, csrf

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
PASSWORD = "Account-fixture-password-123!"


@pytest.fixture(autouse=True)
def offline(requests_mock, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return requests_mock


@pytest.fixture
def accounts(client):
    owner = get_user_model().objects.create_user(
        username="settings-owner", email="owner@example.invalid", password=PASSWORD
    )
    other = get_user_model().objects.create_user(
        username="settings-other", email="other@example.invalid", password=PASSWORD
    )
    other.profile.measurements_format = "Europe"
    other.profile.save(update_fields=["measurements_format"])
    client.force_login(owner)
    return SimpleNamespace(owner=owner, other=other)


def endpoint():
    return reverse("api_v1:account")


def patch(client, body, **headers):
    return client.patch(endpoint(), json.dumps(body), content_type="application/json", **headers)


def snapshot():
    return {
        model: list(model.objects.order_by("pk").values()) for model in (get_user_model(), Profile)
    }


def profile_post(client, user, **changes):
    return client.post(
        reverse("profile"),
        {"username": user.username, "email": user.email, "measurements_format": "USA", **changes},
    )


def test_get_is_owned_private_bounded_and_contains_only_explicit_account_fields(
    client, accounts, django_assert_num_queries, offline
):
    before = snapshot()
    with django_assert_num_queries(6):
        response = client.get(endpoint())
    assert response.status_code == 200
    assert response.json() == {
        "id": accounts.owner.pk,
        "username": "settings-owner",
        "email": "owner@example.invalid",
        "profile": {"measurements_format": "USA", "image_url": accounts.owner.profile.image.url},
    }
    assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
    assert "cookie" in response["Vary"].lower() and response["X-Request-ID"]
    assert snapshot() == before and not offline.called
    client.force_login(accounts.other)
    assert client.get(endpoint()).json()["email"] == accounts.other.email
    assert client.get(endpoint()).json()["profile"]["measurements_format"] == "Europe"


@pytest.mark.parametrize(
    "body",
    [
        {"username": "new-owner"},
        {"email": "new@example.invalid"},
        {"measurements_format": "Europe"},
        {"username": "new-owner", "email": "new@example.invalid", "measurements_format": "Europe"},
    ],
)
def test_patch_is_partial_repeatable_and_preserves_other_accounts_and_security_fields(
    client, accounts, body
):
    before_user = get_user_model().objects.values().get(pk=accounts.owner.pk)
    before_profile = Profile.objects.values().get(user=accounts.owner)
    other_user = get_user_model().objects.values().get(pk=accounts.other.pk)
    other_profile = Profile.objects.values().get(user=accounts.other)
    cookie = client.session.session_key
    for _ in range(2):
        response = patch(client, body)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == body.get("username", before_user["username"])
        assert data["email"] == body.get("email", before_user["email"])
        assert data["profile"]["measurements_format"] == body.get(
            "measurements_format", before_profile["measurements_format"]
        )
    current = get_user_model().objects.values().get(pk=accounts.owner.pk)
    for field in set(before_user) - {"username", "email"}:
        assert current[field] == before_user[field]
    assert get_user_model().objects.values().get(pk=accounts.other.pk) == other_user
    assert Profile.objects.values().get(user=accounts.other) == other_profile
    assert client.session.session_key == cookie
    assert client.get(reverse("api_v1:auth-session")).json()["user"]["username"] == data["username"]


def test_empty_patch_is_a_noop_without_domain_updates(client, accounts):
    before = snapshot()

    def no_writes(execute, sql, params, many, context):
        assert not sql.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE"))
        return execute(sql, params, many, context)

    with connection.execute_wrapper(no_writes):
        assert patch(client, {}).status_code == 200
    assert snapshot() == before


def test_partial_update_does_not_revalidate_or_save_omitted_legacy_values(client, accounts):
    get_user_model().objects.filter(pk=accounts.owner.pk).update(email="")
    assert patch(client, {"measurements_format": "Europe"}).status_code == 200
    assert patch(client, {"username": "renamed"}).json()["email"] == ""
    get_user_model().objects.filter(pk=accounts.owner.pk).update(email="Legacy@EXAMPLE.invalid")
    response = patch(client, {"username": "rename-again"})
    assert response.status_code == 200 and response.json()["email"] == "Legacy@EXAMPLE.invalid"
    accounts.owner.refresh_from_db()
    assert accounts.owner.email == "Legacy@EXAMPLE.invalid"


def test_username_and_email_form_normalization_and_case_insensitive_collision(client, accounts):
    response = patch(client, {"username": "  Ｎｏｒｍａｌ  ", "email": "New@EXAMPLE.invalid"})
    assert response.status_code == 200 and response.json()["username"] == "Normal"
    assert response.json()["email"] == "New@example.invalid"
    assert patch(client, {"username": "NORMAL"}).status_code == 200
    before = snapshot()
    response = patch(
        client,
        {
            "username": "SETTINGS-OTHER",
            "email": "attempt@example.invalid",
            "measurements_format": "Europe",
        },
    )
    assert response.status_code == 400 and "username" in response.json()["error"]["fields"]
    assert snapshot() == before


@pytest.mark.parametrize(
    "body",
    [
        {"username": ""},
        {"username": "bad name"},
        {"username": "x" * 151},
        {"username": 123},
        {"username": None},
        {"email": ""},
        {"email": "not-email"},
        {"email": False},
        {"email": []},
        {"measurements_format": "EUROPE"},
        {"measurements_format": ""},
        {"measurements_format": None},
        {"id": 999},
        {"user_id": 999},
        {"profile": {"measurements_format": "Europe"}},
        {"password": "new-password"},
        {"is_staff": True},
        {"is_active": False},
        {"groups": [1]},
        {"image": "anything.png"},
        {"image_url": "https://untrusted.invalid/pic"},
        [],
        None,
    ],
)
def test_invalid_and_injected_updates_are_rejected_without_writes(client, accounts, body):
    before = snapshot()
    response = patch(client, body)
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"
    assert snapshot() == before


def test_invalid_preference_rolls_back_all_account_fields_and_html_uses_same_policy(
    client, accounts
):
    before = snapshot()
    response = patch(
        client,
        {
            "username": "attempt",
            "email": "attempt@example.invalid",
            "measurements_format": "invalid",
        },
    )
    assert response.status_code == 400 and snapshot() == before
    response = profile_post(client, accounts.owner, username="SETTINGS-OTHER")
    assert response.status_code == 200 and "username" in response.context["u_form"].errors
    assert snapshot() == before
    response = profile_post(
        client, accounts.owner, username="from-html", measurements_format="Europe"
    )
    assert response.status_code == 302
    data = client.get(endpoint()).json()
    assert data["username"] == "from-html" and data["profile"]["measurements_format"] == "Europe"


def test_image_url_is_read_only_and_image_data_is_not_accessed_or_written(
    client, accounts, monkeypatch
):
    field = Profile.objects.get(user=accounts.owner).image

    def fail(*args, **kwargs):
        raise AssertionError("Image bytes/storage writes must not be used")

    monkeypatch.setattr(field.storage, "open", fail)
    monkeypatch.setattr(field.storage, "save", fail)
    before = field.name
    assert patch(client, {"email": "changed@example.invalid"}).status_code == 200
    assert Profile.objects.get(user=accounts.owner).image.name == before
    assert client.get(endpoint()).json()["profile"]["image_url"] == field.url


def test_missing_profile_is_explicit_and_never_repaired_by_reads_or_patch(client, accounts):
    Profile.objects.filter(user=accounts.owner).delete()
    before = snapshot()
    assert client.get(endpoint()).json()["profile"] is None
    for body in ({}, {"email": "attempt@example.invalid"}, {"measurements_format": "Europe"}):
        response = patch(client, body)
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "account_profile_unavailable"
        )
    assert snapshot() == before


def test_invalid_saved_units_are_unknown_until_explicitly_replaced(client, accounts):
    Profile.objects.filter(user=accounts.owner).update(measurements_format="legacy-invalid")
    assert client.get(endpoint()).json()["profile"]["measurements_format"] is None
    assert (
        patch(client, {"email": "changed@example.invalid"}).json()["profile"]["measurements_format"]
        is None
    )
    assert Profile.objects.get(user=accounts.owner).measurements_format == "legacy-invalid"
    assert (
        patch(client, {"measurements_format": "Europe"}).json()["profile"]["measurements_format"]
        == "Europe"
    )


@pytest.mark.parametrize("method", ["get", "patch"])
def test_anonymous_requests_cannot_read_or_change_accounts(client, accounts, method):
    client.logout()
    before = snapshot()
    response = (
        client.get(endpoint())
        if method == "get"
        else patch(client, {"email": "attempt@example.invalid"})
    )
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "authentication_required"
    )
    assert snapshot() == before


@pytest.mark.parametrize("storage", ["cookie", "http_only", "session"])
def test_csrf_is_required_and_session_token_remains_valid_after_patch(accounts, settings, storage):
    settings.CSRF_COOKIE_HTTPONLY = storage == "http_only"
    settings.CSRF_USE_SESSIONS = storage == "session"
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(accounts.owner)
    assert patch(strict, {"email": "new@example.invalid"}).status_code == 403
    token = csrf(strict)
    assert (
        patch(strict, {"email": "new@example.invalid"}, HTTP_X_CSRFTOKEN=token).status_code == 200
    )
    assert (
        patch(strict, {"measurements_format": "Europe"}, HTTP_X_CSRFTOKEN=token).status_code == 200
    )
    assert (
        patch(
            strict,
            {"email": "attacker@example.invalid"},
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://untrusted.invalid",
        ).status_code
        == 403
    )


def test_wire_methods_media_queries_and_private_error_headers(client, accounts):
    for method in ("post", "put", "delete"):
        assert getattr(client, method)(endpoint()).status_code == 405
    assert client.patch(endpoint(), "{bad", content_type="application/json").status_code == 400
    assert client.patch(endpoint(), {"email": "new@example.invalid"}).status_code == 415
    assert client.get(endpoint(), {"owner": accounts.other.pk}).status_code == 400
    response = client.patch(endpoint() + "?email=x&email=y", "{}", content_type="application/json")
    assert response.status_code == 400 and "no-store" in response["Cache-Control"]
    assert response["Content-Type"] == "application/json" and response["X-Request-ID"]
    assert client.head(endpoint()).status_code == 200


def test_profile_save_failure_rolls_back_username_email_and_preferences(
    client, accounts, monkeypatch
):
    before = snapshot()

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic profile failure")

    monkeypatch.setattr(Profile, "save", fail)
    client.raise_request_exception = False
    response = patch(
        client,
        {
            "username": "attempt",
            "email": "attempt@example.invalid",
            "measurements_format": "Europe",
        },
    )
    assert response.status_code == 500 and snapshot() == before


def test_serialization_failure_rolls_back_all_fields(client, accounts, monkeypatch):
    before = snapshot()

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic representation failure")

    monkeypatch.setattr("nhl_web_app.api.account.AccountSerializer.to_representation", fail)
    client.raise_request_exception = False
    assert (
        patch(
            client,
            {
                "username": "attempt",
                "email": "attempt@example.invalid",
                "measurements_format": "Europe",
            },
        ).status_code
        == 500
    )
    assert snapshot() == before


def test_email_changes_invalidate_old_reset_links_without_changing_password_or_sessions(
    client, accounts
):
    token = default_token_generator.make_token(accounts.owner)
    password = accounts.owner.password
    session = client.session.session_key
    assert patch(client, {"email": "new@example.invalid"}).status_code == 200
    accounts.owner.refresh_from_db()
    assert not default_token_generator.check_token(accounts.owner, token)
    assert accounts.owner.password == password and client.session.session_key == session


def test_schema_describes_private_partial_json_and_readonly_image(
    client, django_assert_num_queries
):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    methods = schema["paths"]["/api/v1/me/"]
    assert set(methods) == {"get", "patch"}
    assert methods["patch"]["security"] == [{"cookieAuth": []}]
    request_ref = methods["patch"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    request = schema["components"]["schemas"][request_ref.rsplit("/", 1)[-1]]
    assert set(request["properties"]) == {"username", "email", "measurements_format"}
    assert not request.get("required")
    assert "image_url" in schema["components"]["schemas"]["AccountProfile"]["properties"]


def payload_client(client, method, body):
    def send(target, *args, **kwargs):
        kwargs.pop("content_type", None)
        if method == "patch":
            return client.patch(target, json.dumps(body), content_type="application/json", **kwargs)
        return client.post(target, body, **kwargs)

    return SimpleNamespace(**{method: send})


@pytest.mark.django_db(transaction=True)
class TestAccountConcurrency:
    @staticmethod
    def clients(owner, other=None):
        clients = [Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)]
        clients[0].force_login(owner)
        clients[1].force_login(other or owner)
        return clients, [csrf(client) for client in clients]

    @pytest.mark.parametrize("first_html", [None, True, False])
    def test_settings_writers_share_owner_lock_and_preserve_fresh_fields(
        self, accounts, first_html
    ):
        clients, tokens = self.clients(accounts.owner)
        payloads = [{"email": "first@example.invalid"}, {"measurements_format": "Europe"}]
        specs = []
        bound = []
        for index, body in enumerate(payloads):
            html = (index == 0 if first_html else index == 1) if first_html is not None else False
            method = "post" if html else "patch"
            if html:
                body = {
                    "username": accounts.owner.username,
                    "email": accounts.owner.email,
                    "measurements_format": "USA",
                    **body,
                }
            bound.append(payload_client(clients[index], method, body))
            specs.append((method, reverse("profile") if html else endpoint(), tokens[index]))
        a, b = concurrent_changes(bound[0], specs[0], bound[1], specs[1])
        assert a[0] in (200, 302) and b[0] in (200, 302)
        accounts.owner.refresh_from_db()
        assert accounts.owner.profile.measurements_format == "Europe"
        assert accounts.owner.email == (
            "owner@example.invalid" if first_html is False else "first@example.invalid"
        )

    def test_read_waits_for_patch_and_independent_accounts_do_not_block(self, accounts):
        clients, tokens = self.clients(accounts.owner)
        a, b = concurrent_changes(
            payload_client(clients[0], "patch", {"email": "new@example.invalid"}),
            ("patch", endpoint(), tokens[0]),
            clients[1],
            ("get", endpoint(), tokens[1]),
        )
        assert a[0] == b[0] == 200 and b[1]["email"] == "new@example.invalid"
        clients, tokens = self.clients(accounts.owner, accounts.other)
        a, b = concurrent_changes(
            payload_client(clients[0], "patch", {"measurements_format": "Europe"}),
            ("patch", endpoint(), tokens[0]),
            payload_client(clients[1], "patch", {"email": "other-new@example.invalid"}),
            ("patch", endpoint(), tokens[1]),
            same_user=False,
        )
        assert a[0] == b[0] == 200

    @pytest.mark.parametrize("second_html", [True, False])
    def test_case_variant_renames_share_registration_name_lock(self, accounts, second_html):
        clients, tokens = self.clients(accounts.owner, accounts.other)
        body = {"username": "SharedNew"}
        second = {"username": "sharednew"}
        method = "post" if second_html else "patch"
        if second_html:
            second.update(email=accounts.other.email, measurements_format="USA")
        a, b = concurrent_changes(
            payload_client(clients[0], "patch", body),
            ("patch", endpoint(), tokens[0]),
            payload_client(clients[1], method, second),
            (method, reverse("profile") if second_html else endpoint(), tokens[1]),
        )
        assert a[0] == 200 and b[0] == (200 if second_html else 400)
        assert get_user_model().objects.filter(username__iexact="sharednew").count() == 1
        accounts.other.refresh_from_db()
        assert accounts.other.username == "settings-other"

    @pytest.mark.parametrize("registration_html", [True, False])
    def test_rename_and_registration_share_case_insensitive_name_lock(
        self, accounts, registration_html
    ):
        clients, tokens = self.clients(accounts.owner)
        clients[1].logout()
        tokens[1] = csrf(clients[1])
        body = {"username": "SharedNew"}
        registration = {
            "username": "sharednew",
            "email": "registration@example.invalid",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        target = reverse("register") if registration_html else reverse("api_v1:auth-register")
        method = "post"
        if registration_html:
            bound = payload_client(clients[1], method, registration)
        else:

            def submit(target, *args, **kwargs):
                kwargs.pop("content_type", None)
                return clients[1].post(
                    target, json.dumps(registration), content_type="application/json", **kwargs
                )

            bound = SimpleNamespace(post=submit)
        a, b = concurrent_changes(
            payload_client(clients[0], "patch", body),
            ("patch", endpoint(), tokens[0]),
            bound,
            ("post", target, tokens[1]),
        )
        assert a[0] == 200 and b[0] == (200 if registration_html else 400)
        assert get_user_model().objects.count() == 2 and Profile.objects.count() == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("rename_html", [True, False])
def test_registration_winning_name_lock_prevents_case_variant_rename(
    accounts, monkeypatch, rename_html
):
    from users.forms import UserRegisterForm

    saved, attempted, acquired, release = Event(), Event(), Event(), Event()
    original = UserRegisterForm.save

    def hold(form, *args, **kwargs):
        saved.set()
        assert release.wait(15)
        return original(form, *args, **kwargs)

    monkeypatch.setattr(UserRegisterForm, "save", hold)
    registration = {
        "username": "SharedNew",
        "email": "registration@example.invalid",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }

    def first():
        try:
            client = Client(enforce_csrf_checks=True)
            token = csrf(client)
            return client.post(
                reverse("api_v1:auth-register"),
                json.dumps(registration),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            ).status_code
        finally:
            connections.close_all()

    def second():
        try:
            client = Client(enforce_csrf_checks=True)
            client.force_login(accounts.owner)
            token = csrf(client)

            def observe(execute, sql, params, many, context):
                if "pg_advisory_xact_lock" in sql:
                    attempted.set()
                    result = execute(sql, params, many, context)
                    acquired.set()
                    return result
                return execute(sql, params, many, context)

            with connection.execute_wrapper(observe):
                if rename_html:
                    return client.post(
                        reverse("profile"),
                        {
                            "username": "sharednew",
                            "email": accounts.owner.email,
                            "measurements_format": "USA",
                        },
                        HTTP_X_CSRFTOKEN=token,
                    ).status_code
                return patch(client, {"username": "sharednew"}, HTTP_X_CSRFTOKEN=token).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(first)
        try:
            assert saved.wait(10)
            b = pool.submit(second)
            assert attempted.wait(10)
            assert not acquired.wait(0.2)
        finally:
            release.set()
        assert a.result(timeout=15) == 201
        assert b.result(timeout=15) == (200 if rename_html else 400)
    accounts.owner.refresh_from_db()
    assert accounts.owner.username == "settings-owner"
    assert get_user_model().objects.filter(username__iexact="SharedNew").count() == 1


@pytest.mark.django_db(transaction=True)
def test_external_exact_username_constraint_race_is_a_field_error_and_rolls_back(
    client, accounts, monkeypatch
):
    from users.forms import UserUpdateForm

    original = UserUpdateForm.save
    before_user = get_user_model().objects.values().get(pk=accounts.owner.pk)
    before_profile = Profile.objects.values().get(user=accounts.owner)

    def outside_writer():
        try:
            get_user_model().objects.create_user(
                username="external-collision", email="external@example.invalid"
            )
        finally:
            connections.close_all()

    def collide(form, *args, **kwargs):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(outside_writer).result(timeout=10)
        return original(form, *args, **kwargs)

    monkeypatch.setattr(UserUpdateForm, "save", collide)
    response = patch(
        client,
        {
            "username": "external-collision",
            "email": "attempt@example.invalid",
            "measurements_format": "Europe",
        },
    )
    assert response.status_code == 400 and "username" in response.json()["error"]["fields"]
    assert get_user_model().objects.values().get(pk=accounts.owner.pk) == before_user
    assert Profile.objects.values().get(user=accounts.owner) == before_profile
