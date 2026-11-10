"""Password recovery over synthetic accounts and an in-memory mail backend."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import re
from threading import Event
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.db import connection, connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
import pytest

from players.models import Skater, Team, LoaderRun, LoaderScheduleState
from users.models import Profile

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
OLD_PASSWORD = "original-recovery-password-583"
NEW_PASSWORD = "replacement-recovery-password-914"


@pytest.fixture(autouse=True)
def recovery_settings(settings, requests_mock):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.PASSWORD_RESET_PUBLIC_ORIGIN = "https://stats.example.invalid"
    settings.PASSWORD_RESET_FRONTEND_PATH = ""
    return requests_mock


@pytest.fixture
def account():
    return get_user_model().objects.create_user(
        username="recover-user", email="target@example.invalid", password=OLD_PASSWORD
    )


@pytest.fixture
def browser():
    return Client(enforce_csrf_checks=True)


def endpoint(action="request"):
    return reverse("api_v1:password-reset" + ("-" + action if action != "request" else ""))


def csrf(browser):
    response = browser.get(reverse("api_v1:auth-csrf"))
    assert response.status_code == 200
    return response.json()["csrf_token"]


def post(browser, action, body, *, token=None, **kwargs):
    return browser.post(
        endpoint(action),
        json.dumps(body),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token or csrf(browser),
        **kwargs,
    )


def link_data(account):
    return {
        "uidb64": urlsafe_base64_encode(force_bytes(account.pk)),
        "token": default_token_generator.make_token(account),
    }


def passwords(link, password=NEW_PASSWORD):
    return {**link, "new_password1": password, "new_password2": password}


def request_reset(browser, email="target@example.invalid", **kwargs):
    return post(browser, "request", {"email": email}, **kwargs)


def email_link(message):
    return re.search(r"https?://\S+", message.body).group(0)


def test_request_uses_trusted_origin_and_legacy_link_then_json_reset_and_login_work(
    browser, account, mailoutbox, recovery_settings
):
    response = request_reset(browser)
    assert response.status_code == 200 and response.json() == {"accepted": True}
    assert len(mailoutbox) == 1 and mailoutbox[0].to == [account.email]
    link = email_link(mailoutbox[0])
    assert link.startswith("https://stats.example.invalid/password-reset-confirm/")
    path = urlparse(link).path.strip("/").split("/")
    data = {"uidb64": path[-2], "token": path[-1]}
    assert post(browser, "validate", data).json() == {"valid": True}
    assert post(browser, "confirm", passwords(data)).json() == {
        "password_reset": True,
        "login_required": True,
    }
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD) and not account.check_password(OLD_PASSWORD)
    assert not browser.get(reverse("api_v1:auth-session")).json()["authenticated"]
    token = csrf(browser)
    login = browser.post(
        reverse("api_v1:auth-login"),
        json.dumps({"username": account.username, "password": NEW_PASSWORD}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert login.status_code == 200
    assert not recovery_settings.called


@pytest.mark.parametrize("kind", ["unknown", "inactive", "unusable", "eligible"])
def test_recovery_acknowledgement_does_not_disclose_eligibility(browser, account, mailoutbox, kind):
    email = account.email
    if kind == "unknown":
        email = "unknown@example.invalid"
    elif kind == "inactive":
        account.is_active = False
        account.save()
    elif kind == "unusable":
        account.set_unusable_password()
        account.save()
    response = request_reset(browser, email)
    assert response.status_code == 200 and response.json() == {"accepted": True}
    assert len(mailoutbox) == (1 if kind == "eligible" else 0)
    assert "email" not in response.content.decode() and "token" not in response.content.decode()


def test_all_matching_eligible_accounts_receive_their_own_link(browser, account, mailoutbox):
    second = get_user_model().objects.create_user(
        username="second", email=account.email, password=OLD_PASSWORD
    )
    request_reset(browser, "TARGET@EXAMPLE.INVALID")
    assert len(mailoutbox) == 2
    ids = {urlparse(email_link(message)).path.strip("/").split("/")[-2] for message in mailoutbox}
    assert ids == {link_data(account)["uidb64"], link_data(second)["uidb64"]}


def test_host_and_forwarded_headers_cannot_poison_links(browser, account, settings, mailoutbox):
    settings.ALLOWED_HOSTS = ["*"]
    settings.USE_X_FORWARDED_HOST = True
    response = request_reset(
        browser, HTTP_HOST="attacker.invalid", HTTP_X_FORWARDED_HOST="forwarded.invalid"
    )
    assert response.status_code == 200
    link = email_link(mailoutbox[0])
    assert urlparse(link).netloc == "stats.example.invalid"
    assert (
        "attacker.invalid" not in mailoutbox[0].body
        and "forwarded.invalid" not in mailoutbox[0].body
    )


def test_frontend_link_keeps_secrets_in_fragment_and_can_be_confirmed(
    browser, account, settings, mailoutbox
):
    settings.PASSWORD_RESET_FRONTEND_PATH = "/recover-password/"
    request_reset(browser)
    parsed = urlparse(email_link(mailoutbox[0]))
    assert parsed.path == "/recover-password/" and parsed.query == ""
    link = {key: values[0] for key, values in parse_qs(parsed.fragment).items()}
    assert post(browser, "confirm", passwords(link)).status_code == 200


@pytest.mark.parametrize(
    "origin,path",
    [
        ("", ""),
        ("https://user:pass@example.invalid", ""),
        ("http://stats.example.invalid", ""),
        ("https://stats.example.invalid/path", ""),
        ("https://stats.example.invalid?secret=x", ""),
        ("https://stats.example.invalid:99999", ""),
        ("https://stats.example.invalid", "//attacker.invalid"),
        ("https://stats.example.invalid", "/reset?next=x"),
        ("https://stats.example.invalid", "/reset#token=x"),
        ("https://stats.example.invalid", "/reset\\bad"),
    ],
)
def test_unsafe_or_missing_configuration_fails_uniformly_before_account_matching(
    browser, account, settings, origin, path, mailoutbox, monkeypatch
):
    settings.PASSWORD_RESET_PUBLIC_ORIGIN = origin
    settings.PASSWORD_RESET_FRONTEND_PATH = path

    def no_lookup(*args, **kwargs):
        raise AssertionError("Configuration must be validated before account matching")

    monkeypatch.setattr("django.contrib.auth.forms.PasswordResetForm.get_users", no_lookup)
    known = request_reset(browser)
    unknown = request_reset(browser, "unknown@example.invalid")
    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()
    assert known.json()["error"]["code"] == "password_reset_unavailable"
    assert not mailoutbox


def test_debug_loopback_http_is_supported_but_not_public_http(
    browser, account, settings, mailoutbox
):
    settings.DEBUG = True
    settings.MIDDLEWARE = [
        item for item in settings.MIDDLEWARE if not item.startswith("debug_toolbar.")
    ]
    settings.PASSWORD_RESET_PUBLIC_ORIGIN = "http://localhost:8000/"
    assert request_reset(browser).status_code == 200
    assert email_link(mailoutbox[0]).startswith("http://localhost:8000/")


def test_delivery_failure_is_generic_and_logs_only_exception_type(
    browser, account, monkeypatch, caplog
):
    def fail(message):
        raise RuntimeError("sensitive-delivery-content " + message.body + account.email)

    monkeypatch.setattr("users.password_recovery.EmailMessage.send", fail)
    response = request_reset(browser)
    assert response.status_code == 200 and response.json() == {"accepted": True}
    assert "RuntimeError" in caplog.text
    assert account.email not in caplog.text and "sensitive-delivery-content" not in caplog.text


@pytest.mark.parametrize("action", ["validate", "confirm"])
@pytest.mark.parametrize(
    "damage",
    [
        "uid",
        "unknown",
        "huge",
        "wrong_token",
        "expired",
        "used",
        "inactive",
        "unusable",
        "email_changed",
        "last_login",
    ],
)
def test_invalid_links_share_one_generic_error(
    browser, account, action, damage, monkeypatch, settings
):
    link = link_data(account)
    if damage == "uid":
        link["uidb64"] = "invalid!"
    elif damage == "unknown":
        link["uidb64"] = urlsafe_base64_encode(b"99999999")
    elif damage == "huge":
        link["uidb64"] = urlsafe_base64_encode(b"99999999999999999999999999999999")
    elif damage == "wrong_token":
        link["token"] += "x"
    elif damage == "expired":
        now = default_token_generator._now()
        monkeypatch.setattr(
            default_token_generator,
            "_now",
            lambda: now + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1),
        )
    elif damage == "used":
        account.set_password("another-current-password-472")
        account.save()
    elif damage == "inactive":
        account.is_active = False
        account.save()
    elif damage == "unusable":
        account.set_unusable_password()
        account.save()
    elif damage == "email_changed":
        account.email = "changed@example.invalid"
        account.save()
    else:
        account.last_login = timezone.make_aware(datetime(2026, 1, 1))
        account.save()
    response = post(browser, action, passwords(link) if action == "confirm" else link)
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_reset_token",
            "message": "This password reset link is invalid or has expired.",
        }
    }
    assert link["token"] not in response.content.decode()


def test_password_validation_failure_does_not_consume_the_token(browser, account):
    link = link_data(account)
    original = account.password
    invalid = passwords(link)
    invalid["new_password2"] = "mismatch"
    response = post(browser, "confirm", invalid)
    assert response.status_code == 400 and "new_password2" in response.json()["error"]["fields"]
    assert post(browser, "confirm", passwords(link, "short")).status_code == 400
    account.refresh_from_db()
    assert account.password == original and default_token_generator.check_token(
        account, link["token"]
    )
    assert post(browser, "confirm", passwords(link)).status_code == 200
    assert (
        post(browser, "confirm", passwords(link)).json()["error"]["code"] == "invalid_reset_token"
    )


def test_target_sessions_are_invalidated_and_other_caller_identity_is_preserved(browser, account):
    first, second = Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)
    first.force_login(account)
    second.force_login(account)
    account.refresh_from_db()
    other = get_user_model().objects.create_user(username="other", password=OLD_PASSWORD)
    browser.force_login(other)
    player = Skater.objects.create(nhl_id=1, name="Owned", birth_date="2000-01-01", games=0)
    account.favorite_skaters.add(player)
    old_key = browser.session.session_key
    assert post(browser, "confirm", passwords(link_data(account))).status_code == 200
    for client in (first, second):
        assert not client.get(reverse("api_v1:auth-session")).json()["authenticated"]
    assert browser.get(reverse("api_v1:auth-session")).json()["user"]["id"] == other.pk
    assert (
        browser.session.session_key == old_key
        and account.favorite_skaters.filter(pk=player.pk).exists()
    )


@pytest.mark.parametrize("mode", ["http_only", "session"])
def test_csrf_modes_work_for_recovery_confirmation(browser, account, settings, mode):
    settings.CSRF_COOKIE_HTTPONLY = mode == "http_only"
    settings.CSRF_USE_SESSIONS = mode == "session"
    assert post(browser, "confirm", passwords(link_data(account))).status_code == 200


def test_secret_key_fallback_and_exact_password_whitespace_remain_django_compatible(
    browser, account, settings
):
    link = link_data(account)
    settings.SECRET_KEY_FALLBACKS = [settings.SECRET_KEY]
    settings.SECRET_KEY = "new-synthetic-secret"
    password = "  replacement-with-spaces-914  "
    assert post(browser, "confirm", passwords(link, password)).status_code == 200
    account.refresh_from_db()
    assert account.check_password(password) and not account.check_password(password.strip())


@pytest.mark.parametrize("action", ["request", "validate", "confirm"])
def test_csrf_precedes_recovery_work_and_get_cannot_mutate(browser, account, action, monkeypatch):
    def no_work(*args, **kwargs):
        raise AssertionError("Missing CSRF must precede recovery work")

    for name in ("send_recovery_instructions", "consume_reset_link", "validate_reset_link"):
        monkeypatch.setattr("nhl_web_app.api.password_recovery." + name, no_work)
    body = (
        {"email": account.email}
        if action == "request"
        else passwords(link_data(account))
        if action == "confirm"
        else link_data(account)
    )
    response = browser.post(endpoint(action), json.dumps(body), content_type="application/json")
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"
    assert browser.get(endpoint(action)).status_code == 405


@pytest.mark.parametrize(
    "action,body",
    [
        ("request", {"email": "bad"}),
        ("request", {"email": 123}),
        ("request", {"email": "a@example.invalid", "domain": "attacker.invalid"}),
        ("validate", {"uidb64": 1, "token": "x"}),
        ("validate", {"uidb64": "x", "token": ""}),
        ("confirm", {"uidb64": "x", "token": "t", "new_password1": 123, "new_password2": "p"}),
        ("confirm", {"uidb64": "x", "token": "t", "next": "https://attacker.invalid"}),
    ],
)
def test_bad_input_is_a_typed_error_without_domain_changes(browser, action, body):
    response = post(browser, action, body)
    assert response.status_code == 400
    assert not get_user_model().objects.exists() and not Profile.objects.exists()


@pytest.mark.parametrize("action", ["request", "validate", "confirm"])
def test_media_queries_and_errors_are_private_json(browser, account, action):
    body = (
        {"email": account.email}
        if action == "request"
        else passwords(link_data(account))
        if action == "confirm"
        else link_data(account)
    )
    token = csrf(browser)
    form = browser.post(endpoint(action), body, HTTP_X_CSRFTOKEN=token)
    assert form.status_code == 415
    query = browser.post(
        endpoint(action) + "?next=/&next=/",
        json.dumps(body),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert query.status_code == 400
    assert "no-store" in query["Cache-Control"] and "cookie" in query["Vary"].lower()
    assert query["Content-Type"] == "application/json" and query["X-Request-ID"]


def test_failed_save_rolls_back_password_and_returns_no_secrets(
    browser, account, monkeypatch, caplog
):
    original = account.password
    original_save = Profile.save

    def fail(profile, *args, **kwargs):
        raise RuntimeError("synthetic-profile-save-failure")

    monkeypatch.setattr(Profile, "save", fail)
    browser.raise_request_exception = False
    link = link_data(account)
    response = post(browser, "confirm", passwords(link))
    assert response.status_code == 500 and response.json()["error"]["code"] == "server_error"
    account.refresh_from_db()
    assert account.password == original
    assert NEW_PASSWORD not in caplog.text and link["token"] not in caplog.text
    monkeypatch.setattr(Profile, "save", original_save)
    assert post(browser, "confirm", passwords(link)).status_code == 200


def test_schema_contains_recovery_requests_private_passwords_and_shared_errors(
    client, django_assert_num_queries
):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    for suffix in ("", "validate/", "confirm/"):
        operation = schema["paths"]["/api/v1/auth/password-reset/" + suffix]["post"]
        assert next(param for param in operation["parameters"] if param["name"] == "X-CSRFToken")[
            "required"
        ]
        assert {"200", "400", "403", "415"} <= operation["responses"].keys()
    fields = schema["components"]["schemas"]["NewPasswordRequest"]["properties"]
    assert all(fields[name]["writeOnly"] for name in ("token", "new_password1", "new_password2"))


def test_stale_profile_edit_cannot_restore_password_after_reset(browser, account):
    from users.forms import UserUpdateForm

    stale = get_user_model().objects.get(pk=account.pk)
    form = UserUpdateForm(
        {"username": account.username, "email": "updated@example.invalid"}, instance=stale
    )
    assert form.is_valid()
    assert post(browser, "confirm", passwords(link_data(account))).status_code == 200
    form.save()
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD) and not account.check_password(OLD_PASSWORD)
    assert account.email == "updated@example.invalid"


def test_api_mail_link_still_completes_on_existing_html_page(browser, account, mailoutbox):
    request_reset(browser)
    path = urlparse(email_link(mailoutbox[0])).path
    redirect = browser.get(path)
    assert redirect.status_code == 302
    page = browser.get(redirect.url)
    assert page.status_code == 200 and page.context["validlink"]
    response = browser.post(
        redirect.url,
        {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        HTTP_X_CSRFTOKEN=csrf(browser),
    )
    assert response.status_code == 302 and response.url == reverse("password_reset_complete")
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("first_flow", ["api", "html"])
def test_api_and_html_cannot_both_consume_the_same_token(monkeypatch, first_flow):
    account = get_user_model().objects.create_user(
        username="race-reset", email="race@example.invalid", password=OLD_PASSWORD
    )
    link = link_data(account)
    first_ready, release = Event(), Event()
    attempted, acquired = Event(), Event()
    original_save = SetPasswordForm.save

    def slow_first(form, *args, **kwargs):
        if form.cleaned_data["new_password1"] == NEW_PASSWORD:
            first_ready.set()
            assert release.wait(15), "First reset was not released"
        return original_save(form, *args, **kwargs)

    monkeypatch.setattr(SetPasswordForm, "save", slow_first)

    def worker(flow, password, watch=False):
        connections.close_all()
        try:
            client = Client(enforce_csrf_checks=True)
            token = csrf(client)
            html_path = None
            if flow == "html":
                response = client.get(
                    reverse(
                        "password_reset_confirm",
                        kwargs={"uidb64": link["uidb64"], "token": link["token"]},
                    )
                )
                assert response.status_code == 302
                html_path = response.url

            def observe(execute, sql, params, many, context):
                if "FOR UPDATE" in sql:
                    attempted.set()
                    result = execute(sql, params, many, context)
                    acquired.set()
                    return result
                return execute(sql, params, many, context)

            def submit():
                if flow == "api":
                    return post(client, "confirm", passwords(link, password), token=token)
                return client.post(
                    html_path,
                    {"new_password1": password, "new_password2": password},
                    HTTP_X_CSRFTOKEN=token,
                )

            if watch:
                with connection.execute_wrapper(observe):
                    response = submit()
            else:
                response = submit()
            return response.status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker, first_flow, NEW_PASSWORD)
        try:
            assert first_ready.wait(15)
            second_flow = "html" if first_flow == "api" else "api"
            second = pool.submit(worker, second_flow, "losing-password-628", True)
            assert attempted.wait(15)
            assert not acquired.wait(0.2), "Second reset should wait for the user lock"
        finally:
            release.set()
        assert first.result(timeout=15) == (200 if first_flow == "api" else 302)
        assert second.result(timeout=15) == (200 if second_flow == "html" else 400)
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD) and not account.check_password(
        "losing-password-628"
    )
    assert not default_token_generator.check_token(account, link["token"])


def test_zero_message_delivery_is_logged_without_changing_acknowledgement(
    browser, account, monkeypatch, caplog
):
    monkeypatch.setattr("users.password_recovery.EmailMessage.send", lambda message: 0)
    response = request_reset(browser)
    assert response.status_code == 200 and response.json() == {"accepted": True}
    assert "did not report a sent message" in caplog.text
    assert account.email not in caplog.text


def test_resetting_to_the_same_password_still_consumes_the_token(browser, account):
    link, old_hash = link_data(account), account.password
    assert post(browser, "confirm", passwords(link, OLD_PASSWORD)).status_code == 200
    account.refresh_from_db()
    assert account.check_password(OLD_PASSWORD) and account.password != old_hash
    assert (
        post(browser, "confirm", passwords(link)).json()["error"]["code"] == "invalid_reset_token"
    )
