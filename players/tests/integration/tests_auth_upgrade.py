"""Form rendering and session/CSRF behavior across the Django upgrade."""

from html.parser import HTMLParser
from io import BytesIO
from types import ModuleType
import sys
import re
from urllib.parse import urlsplit

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.base import ContentFile
from django.test import Client
from django.urls import include, path, reverse
from PIL import Image


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class Forms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "form":
            assert self.current is None, "Nested forms break browser submissions"
            self.current = dict(attrs, inputs={})
            self.forms.append(self.current)
        elif tag in {"input", "select"} and self.current is not None and "name" in attrs:
            self.current["inputs"][attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


@pytest.fixture
def account():
    return User.objects.create_user(
        username="upgrade-user", password="synthetic-password-123", email="user@example.invalid"
    )


@pytest.mark.parametrize(
    "route, expected_inputs",
    [
        ("login", {"username", "password"}),
        ("register", {"username", "email", "password1", "password2"}),
        ("password_reset", {"email"}),
    ],
)
def test_public_auth_forms_render_with_csrf(client, route, expected_inputs):
    response = client.get(reverse(route))
    assert response.status_code == 200
    forms = Forms(response.content.decode()).forms
    assert any(expected_inputs <= form["inputs"].keys() for form in forms)
    assert response.cookies["csrftoken"].value


def test_registration_creates_a_user_and_profile(client):
    response = client.post(
        reverse("register"),
        {
            "username": "new-upgrade-user",
            "email": "new@example.invalid",
            "password1": "synthetic-password-123",
            "password2": "synthetic-password-123",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("login")
    user = User.objects.get(username="new-upgrade-user")
    assert user.check_password("synthetic-password-123")
    assert user.profile.measurements_format == "USA"


def test_same_origin_https_login_accepts_csrf_and_preserves_next(account):
    client = Client(enforce_csrf_checks=True)
    response = client.get(reverse("login"), secure=True)
    token = response.cookies["csrftoken"].value
    destination = reverse("players") + "?season=20262027"
    response = client.post(
        reverse("login"),
        {"username": account.username, "password": "synthetic-password-123", "next": destination},
        secure=True,
        HTTP_ORIGIN="https://testserver",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 302
    assert response.url == destination
    assert int(client.session["_auth_user_id"]) == account.pk


def test_password_reset_email_link_changes_password_and_allows_login(
    client, account, settings, mailoutbox
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    response = client.post(reverse("password_reset"), {"email": account.email})
    assert response.status_code == 302
    assert response.url == reverse("password_reset_done")
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [account.email]
    link = re.search(r"https?://\S+", mailoutbox[0].body).group(0)

    response = client.get(urlsplit(link).path)
    assert response.status_code == 302
    form_url = response.url
    assert client.get(form_url).context["validlink"] is True
    password = "replacement-synthetic-password-456"
    response = client.post(form_url, {"new_password1": password, "new_password2": password})
    assert response.status_code == 302
    assert response.url == reverse("password_reset_complete")
    account.refresh_from_db()
    assert account.check_password(password)
    assert client.login(username=account.username, password=password)


def test_password_reset_for_unknown_email_does_not_send_mail(client, settings, mailoutbox):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    response = client.post(reverse("password_reset"), {"email": "unknown@example.invalid"})
    assert response.status_code == 302
    assert response.url == reverse("password_reset_done")
    assert not mailoutbox


def test_profile_renders_bootstrap_forms_for_a_signed_in_user(client, account):
    client.force_login(account)
    response = client.get(reverse("profile"))
    assert response.status_code == 200
    forms = Forms(response.content.decode()).forms
    assert any(
        {"username", "email", "image", "measurements_format"} <= form["inputs"].keys()
        for form in forms
    )


@pytest.mark.parametrize(
    "format_, suffix, mime",
    [("PNG", "png", "image/png"), ("JPEG", "jpg", "image/jpeg"), ("WEBP", "webp", "image/webp")],
)
def test_profile_upload_saves_a_valid_image_and_account_edits(
    client, account, settings, tmp_path, format_, suffix, mime
):
    settings.MEDIA_ROOT = str(tmp_path)
    image = BytesIO()
    Image.new("RGB", (2, 3), (10, 20, 30)).save(image, format=format_)
    original = image.getvalue()
    upload = SimpleUploadedFile("avatar." + suffix, original, content_type=mime)
    client.force_login(account)

    response = client.post(
        reverse("profile"),
        {
            "username": account.username,
            "email": "updated@example.invalid",
            "measurements_format": "Europe",
            "image": upload,
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("profile")
    account.refresh_from_db()
    assert account.email == "updated@example.invalid"
    assert account.profile.measurements_format == "Europe"
    with Image.open(account.profile.image.path) as saved:
        saved.load()
        assert saved.format == format_
        assert saved.size == (2, 3)
        if format_ == "PNG":
            assert saved.getpixel((0, 0)) == (10, 20, 30)
    with account.profile.image.open("rb") as saved:
        assert saved.read() == original


@pytest.mark.parametrize("existing_avatar", [False, True])
@pytest.mark.parametrize("invalid", ["garbage", "svg", "truncated", "pixel-limit"])
def test_invalid_profile_image_keeps_existing_account_values(
    client, account, settings, tmp_path, monkeypatch, existing_avatar, invalid
):
    settings.MEDIA_ROOT = str(tmp_path)
    image = BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(image, format="PNG")
    if existing_avatar:
        account.profile.image.save("existing.png", ContentFile(image.getvalue()))
    original_name = account.profile.image.name
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    content = {
        "garbage": b"not an image",
        "svg": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        "truncated": image.getvalue()[:20],
        "pixel-limit": image.getvalue(),
    }[invalid]
    if invalid == "pixel-limit":
        # Exercise Pillow's existing safeguard with a tiny generated image.
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 4)
    client.force_login(account)
    response = client.post(
        reverse("profile"),
        {
            "username": account.username,
            "email": "rejected@example.invalid",
            "measurements_format": "Europe",
            "image": SimpleUploadedFile("avatar.png", content, content_type="image/png"),
        },
    )

    assert response.status_code == 200
    assert "image" in response.context["p_form"].errors
    account.refresh_from_db()
    assert account.email == "user@example.invalid"
    assert account.profile.measurements_format == "USA"
    assert account.profile.image.name == original_name
    assert {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


def test_logout_requires_post_and_csrf_then_returns_to_the_same_page(account):
    client = Client(enforce_csrf_checks=True)
    client.force_login(account)
    response = client.get(reverse("about"))
    logout_form = next(
        form
        for form in Forms(response.content.decode()).forms
        if form.get("action") == reverse("logout")
    )
    assert logout_form["method"].lower() == "post"
    assert logout_form["inputs"]["next"] == reverse("about")

    assert client.get(reverse("logout")).status_code == 405
    assert client.post(reverse("logout")).status_code == 403
    assert "_auth_user_id" in client.session

    response = client.post(reverse("logout"), logout_form["inputs"])
    assert response.status_code == 302
    assert response.url == reverse("about")
    assert "_auth_user_id" not in client.session


def test_logout_does_not_redirect_to_an_external_site(client, account):
    client.force_login(account)
    response = client.post(reverse("logout"), {"next": "https://example.invalid/"})
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert b"logged out" in response.content.lower()


def test_development_home_renders_with_the_debug_toolbar(client, settings, monkeypatch):
    settings.DEBUG = True
    settings.DEBUG_TOOLBAR_CONFIG = {"IS_RUNNING_TESTS": False}
    # URL modules are cached; provide the development route normally added at startup.
    urls = ModuleType("upgrade_debug_urls")
    urls.urlpatterns = [
        path("", include("nhl_web_app.urls")),
        path("__debug__/", include("debug_toolbar.urls")),
    ]
    monkeypatch.setitem(sys.modules, urls.__name__, urls)
    settings.ROOT_URLCONF = urls.__name__

    response = client.get(reverse("home"), REMOTE_ADDR="127.0.0.1")

    assert response.status_code == 200
    assert b'id="djDebug"' in response.content
