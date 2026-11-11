"""Multipart avatars, shared storage lifecycle and real account-lock races."""

from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connections
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.test.client import MULTIPART_CONTENT, BOUNDARY, encode_multipart
from django.urls import reverse
from PIL import Image
import pytest

from users.models import Profile
from users import profile_images
from players.tests.integration.tests_favorites_api_db import concurrent_changes, csrf

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return requests_mock


@pytest.fixture
def avatars(client):
    owner = get_user_model().objects.create_user(
        username="avatar-owner", email="owner@example.invalid"
    )
    other = get_user_model().objects.create_user(
        username="avatar-other", email="other@example.invalid"
    )
    client.force_login(owner)
    return SimpleNamespace(owner=owner, other=other)


def content(format_="PNG", size=(3, 4)):
    stream = BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(stream, format=format_)
    return stream.getvalue()


def upload(client, format_="PNG", raw=None, name="avatar.png", **headers):
    raw = content(format_) if raw is None else raw
    file = SimpleUploadedFile(name, raw, content_type="application/octet-stream")
    return client.put(
        reverse("api_v1:account-image"),
        encode_multipart(BOUNDARY, {"image": file}),
        content_type=MULTIPART_CONTENT,
        **headers,
    )


def files(tmp_path):
    return {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }


def records():
    return {
        model: list(model.objects.order_by("pk").values()) for model in (get_user_model(), Profile)
    }


def current(user):
    return Profile.objects.get(user=user)


def old_image(user, name="existing.png"):
    profile = current(user)
    profile.image.save(name, ContentFile(content()), save=True)
    return profile.image.name


@pytest.mark.parametrize("format_,suffix", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")])
def test_upload_validates_actual_content_and_uses_generated_names_without_other_changes(
    client, avatars, tmp_path, django_capture_on_commit_callbacks, format_, suffix, offline
):
    before = records()
    original = content(format_)
    with django_capture_on_commit_callbacks(execute=True):
        response = upload(client, format_, name="../../pretend.html", raw=original)
    assert response.status_code == 200
    profile = current(avatars.owner)
    assert profile.image.name.startswith("profile_pics/") and profile.image.name.endswith(
        "." + suffix
    )
    assert "pretend" not in profile.image.name and ".." not in profile.image.name
    assert files(tmp_path) == {profile.image.name: original}
    with profile.image.open("rb") as stored:
        assert stored.read() == original
    assert response.json()["profile"]["image_url"] == profile.image.url
    assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
    assert "cookie" in response["Vary"].lower() and response["X-Request-ID"]
    after = records()
    assert after[get_user_model()] == before[get_user_model()]
    owner_before = next(row for row in before[Profile] if row["user_id"] == avatars.owner.pk)
    owner_after = next(row for row in after[Profile] if row["user_id"] == avatars.owner.pk)
    assert {key: value for key, value in owner_before.items() if key != "image"} == {
        key: value for key, value in owner_after.items() if key != "image"
    }
    assert current(avatars.other).image.name == "default.jpg" and not offline.called


def test_replace_deletes_old_file_only_after_commit_and_repeated_uploads_leave_one_active_file(
    client, avatars, tmp_path, django_capture_on_commit_callbacks
):
    old = old_image(avatars.owner)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert upload(client).status_code == 200
        assert old in files(tmp_path)
        assert len(files(tmp_path)) == 2
    first = current(avatars.owner).image.name
    assert old not in files(tmp_path) and len(callbacks) == 1
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(client).status_code == 200
    assert current(avatars.owner).image.name != first
    assert list(files(tmp_path)) == [current(avatars.owner).image.name]


def test_delete_restores_default_and_never_deletes_shared_default(
    client, avatars, tmp_path, django_capture_on_commit_callbacks
):
    (tmp_path / "default.jpg").write_bytes(b"shared default fixture")
    old = old_image(avatars.owner)
    for _ in range(2):
        with django_capture_on_commit_callbacks(execute=True):
            response = client.delete(reverse("api_v1:account-image"))
            assert response.status_code == 204 and response.content == b""
        assert current(avatars.owner).image.name == "default.jpg"
    assert files(tmp_path) == {"default.jpg": b"shared default fixture"}
    assert not (tmp_path / old).exists()


def test_file_with_another_profile_reference_is_kept_until_last_reference_is_removed(
    client, avatars, tmp_path, django_capture_on_commit_callbacks
):
    shared = old_image(avatars.owner)
    Profile.objects.filter(user=avatars.other).update(image=shared)
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(client).status_code == 200
    assert shared in files(tmp_path)
    client.force_login(avatars.other)
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete(reverse("api_v1:account-image")).status_code == 204
    assert shared not in files(tmp_path)


def test_unmanaged_legacy_path_is_not_deleted(
    client, avatars, tmp_path, django_capture_on_commit_callbacks
):
    (tmp_path / "legacy-shared.png").write_bytes(content())
    Profile.objects.filter(user=avatars.owner).update(image="legacy-shared.png")
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(client).status_code == 200
    assert (tmp_path / "legacy-shared.png").exists()


@pytest.mark.parametrize(
    "damage",
    [
        "garbage",
        "svg",
        "truncated",
        "gif",
        "animated",
        "empty",
        "too-big",
        "pixels",
        "dimensions",
        "bomb",
    ],
)
def test_bad_uploads_do_not_write_storage_or_change_accounts(
    client, avatars, tmp_path, monkeypatch, damage
):
    old_image(avatars.owner)
    raw = content()
    if damage == "garbage":
        raw = b"not an image"
    elif damage == "svg":
        raw = b"<svg><script>alert(1)</script></svg>"
    elif damage == "truncated":
        raw = raw[:30]
    elif damage == "gif":
        raw = content("GIF")
    elif damage == "animated":
        stream = BytesIO()
        a = Image.new("RGB", (3, 4), (10, 20, 30))
        b = Image.new("RGB", (3, 4), (30, 20, 10))
        a.save(stream, format="WEBP", save_all=True, append_images=[b], duration=100, loop=0)
        raw = stream.getvalue()
    elif damage == "empty":
        raw = b""
    elif damage == "too-big":
        monkeypatch.setattr(profile_images, "MAX_AVATAR_BYTES", len(raw) - 1)
    elif damage == "pixels":
        monkeypatch.setattr(profile_images, "MAX_AVATAR_PIXELS", 11)
    elif damage == "dimensions":
        monkeypatch.setattr(profile_images, "MAX_AVATAR_DIMENSION", 3)
    elif damage == "bomb":
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 7)
    before = records(), files(tmp_path)
    response = upload(client, raw=raw)
    assert response.status_code == 400 and "image" in response.json()["error"]["fields"]
    assert (records(), files(tmp_path)) == before


@pytest.mark.parametrize("body", [{}, {"image": "not a file"}, {"image": "", "user_id": "1"}])
def test_missing_text_and_injected_fields_are_rejected(client, avatars, tmp_path, body):
    before = records(), files(tmp_path)
    response = client.put(
        reverse("api_v1:account-image"),
        encode_multipart(BOUNDARY, body),
        content_type=MULTIPART_CONTENT,
    )
    assert response.status_code == 400 and (records(), files(tmp_path)) == before


def test_extra_and_duplicate_files_are_rejected_before_storage(client, avatars, tmp_path):
    for body in [
        {"image": [SimpleUploadedFile("a.png", content()), SimpleUploadedFile("b.png", content())]},
        {"image": SimpleUploadedFile("a.png", content()), "email": "attempt@example.invalid"},
        {
            "image": SimpleUploadedFile("a.png", content()),
            "extra": SimpleUploadedFile("b.png", content()),
        },
    ]:
        before = records(), files(tmp_path)
        response = client.put(
            reverse("api_v1:account-image"),
            encode_multipart(BOUNDARY, body),
            content_type=MULTIPART_CONTENT,
        )
        assert response.status_code == 400 and (records(), files(tmp_path)) == before


@pytest.mark.parametrize("fault", ["save", "serialization", "url", "storage"])
def test_failures_roll_back_profile_and_remove_new_or_partial_files(
    client, avatars, tmp_path, monkeypatch, fault, django_capture_on_commit_callbacks
):
    old = old_image(avatars.owner)
    before = records(), files(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic avatar failure")

    storage = Profile._meta.get_field("image").storage
    if fault == "save":
        monkeypatch.setattr(Profile, "save", fail)
    elif fault == "serialization":
        monkeypatch.setattr(
            "nhl_web_app.api.account_image.AccountSerializer.to_representation", fail
        )
    elif fault == "url":
        monkeypatch.setattr(storage, "url", fail)
    else:
        original = storage.save

        def partial(name, content, **kwargs):
            original(name, content, **kwargs)
            raise OSError("synthetic failure after storage write")

        monkeypatch.setattr(storage, "save", partial)
    client.raise_request_exception = False
    with django_capture_on_commit_callbacks(execute=True):
        response = upload(client)
    assert response.status_code == 500
    assert (records(), files(tmp_path)) == before and old in files(tmp_path)


def test_cleanup_failure_is_logged_after_commit_without_false_failed_response(
    client, avatars, tmp_path, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    old = old_image(avatars.owner)
    storage = Profile._meta.get_field("image").storage
    original = storage.delete

    def fail_old(name):
        if name == old:
            raise OSError("synthetic cleanup failure")
        original(name)

    monkeypatch.setattr(storage, "delete", fail_old)
    with django_capture_on_commit_callbacks(execute=True):
        response = upload(client)
    assert response.status_code == 200
    assert current(avatars.owner).image.name != old
    assert len(files(tmp_path)) == 2 and "Profile image cleanup failed" in caplog.text


def test_collision_does_not_overwrite_an_existing_file(client, avatars, tmp_path, monkeypatch):
    name = "profile_pics/fixed.png"
    storage = Profile._meta.get_field("image").storage
    storage.save(name, ContentFile(b"protected fixture"))
    monkeypatch.setattr(profile_images, "uuid4", lambda: SimpleNamespace(hex="fixed"))
    before = records(), files(tmp_path)
    client.raise_request_exception = False
    assert upload(client).status_code == 500
    assert (records(), files(tmp_path)) == before


@pytest.mark.parametrize("resource", ["put", "delete"])
def test_missing_profile_returns_conflict_without_backfill_or_files(
    client, avatars, tmp_path, resource
):
    Profile.objects.filter(user=avatars.owner).delete()
    before = records(), files(tmp_path)
    response = (
        upload(client) if resource == "put" else client.delete(reverse("api_v1:account-image"))
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "account_profile_unavailable"
    )
    assert (records(), files(tmp_path)) == before


@pytest.mark.parametrize("resource", ["put", "delete"])
def test_anonymous_writes_are_rejected(client, avatars, tmp_path, resource):
    client.logout()
    before = records(), files(tmp_path)
    response = (
        upload(client) if resource == "put" else client.delete(reverse("api_v1:account-image"))
    )
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "authentication_required"
    )
    assert (records(), files(tmp_path)) == before


@pytest.mark.parametrize("mode", ["cookie", "http_only", "session"])
def test_csrf_upload_and_reset_work_with_all_supported_token_storage(
    avatars, settings, mode, django_capture_on_commit_callbacks
):
    settings.CSRF_USE_SESSIONS = mode == "session"
    settings.CSRF_COOKIE_HTTPONLY = mode == "http_only"
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(avatars.owner)
    assert upload(strict).status_code == 403
    token = csrf(strict)
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(strict, HTTP_X_CSRFTOKEN=token).status_code == 200
    target = reverse("api_v1:account-image")
    assert strict.delete(target).status_code == 403
    assert (
        upload(strict, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://untrusted.invalid").status_code
        == 403
    )
    with django_capture_on_commit_callbacks(execute=True):
        assert strict.delete(target, HTTP_X_CSRFTOKEN=token).status_code == 204
    assert (
        strict.session.session_key
        and strict.get(reverse("api_v1:auth-session")).json()["authenticated"]
    )


def test_wire_format_and_queries_are_strict_without_global_multipart_support(client, avatars):
    target = reverse("api_v1:account-image")
    for method in ("get", "post", "patch"):
        assert getattr(client, method)(target).status_code == 405
    assert client.put(target, "{}", content_type="application/json").status_code == 415
    assert client.put(target, b"bytes", content_type="image/png").status_code == 415
    assert client.put(target, b"body", content_type="multipart/form-data").status_code == 400
    assert client.delete(target + "?user=1").status_code == 400
    assert (
        client.delete(target, '{"clear":true}', content_type="application/json").status_code == 400
    )
    assert client.delete(target, "{}", content_type="application/json").status_code == 204
    assert (
        client.patch(
            reverse("api_v1:account"),
            encode_multipart(BOUNDARY, {"email": "attempt@example.invalid"}),
            content_type=MULTIPART_CONTENT,
        ).status_code
        == 415
    )


def test_schema_put_is_multipart_and_other_endpoints_remain_json(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    methods = schema["paths"]["/api/v1/me/image/"]
    assert set(methods) == {"put", "delete"}
    assert set(methods["put"]["requestBody"]["content"]) == {"multipart/form-data"}
    assert methods["put"]["security"] == [{"cookieAuth": []}]
    assert "content" not in methods["delete"]["responses"]["204"]
    ref = methods["put"]["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"].rsplit(
        "/", 1
    )[-1]
    assert schema["components"]["schemas"][ref]["properties"]["image"]["format"] == "binary"
    assert set(schema["paths"]["/api/v1/me/"]["patch"]["requestBody"]["content"]) == {
        "application/json"
    }


class MemoryImageStorage(Storage):
    def __init__(self):
        self.files = {}

    def _open(self, name, mode="rb"):
        return ContentFile(self.files[name], name=name)

    def _save(self, name, content):
        self.files[name] = b"".join(content.chunks())
        return name

    def exists(self, name):
        return name in self.files

    def delete(self, name):
        self.files.pop(name, None)

    def url(self, name):
        return "/objects/" + name

    def path(self, name):
        raise AssertionError("Storage.path is not supported")


def test_storage_without_local_paths_and_storage_renamed_files_are_supported(
    client, avatars, monkeypatch, django_capture_on_commit_callbacks
):
    class RenamingStorage(MemoryImageStorage):
        def _save(self, name, content):
            return super()._save(name.replace(".png", "_stored.png"), content)

    storage = RenamingStorage()
    monkeypatch.setattr(Profile._meta.get_field("image"), "storage", storage)
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(client).status_code == 200
    name = current(avatars.owner).image.name
    assert name.endswith("_stored.png") and list(storage.files) == [name]
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(client).status_code == 200
    assert len(storage.files) == 1 and name not in storage.files
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete(reverse("api_v1:account-image")).status_code == 204
    assert storage.files == {}


def test_html_replacement_shares_lifecycle_and_retains_original_bytes(
    client, avatars, tmp_path, django_capture_on_commit_callbacks
):
    old = old_image(avatars.owner)
    before_user = get_user_model().objects.values().get(pk=avatars.owner.pk)
    raw = content("WEBP")
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("profile"),
            {
                "username": avatars.owner.username,
                "email": avatars.owner.email,
                "measurements_format": "Europe",
                "image": SimpleUploadedFile("original.webp", raw),
            },
        )
        assert old in files(tmp_path)
    assert response.status_code == 302
    name = current(avatars.owner).image.name
    assert files(tmp_path) == {name: raw} and name.endswith(".webp")
    assert current(avatars.owner).measurements_format == "Europe"
    assert get_user_model().objects.values().get(pk=avatars.owner.pk) == before_user


def test_failed_html_combined_save_cleans_staged_file_and_keeps_old_image(
    client, avatars, tmp_path, monkeypatch
):
    from users.forms import UserUpdateForm

    old_image(avatars.owner)
    before = records(), files(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic HTML save failure")

    monkeypatch.setattr(UserUpdateForm, "save", fail)
    client.raise_request_exception = False
    response = client.post(
        reverse("profile"),
        {
            "username": "attempt",
            "email": avatars.owner.email,
            "measurements_format": "Europe",
            "image": SimpleUploadedFile("avatar.png", content()),
        },
    )
    assert response.status_code == 500 and (records(), files(tmp_path)) == before


def image_client(client, *, html=False):
    def send(target, *args, **kwargs):
        kwargs.pop("content_type", None)
        if html:
            return client.post(
                target,
                {
                    "username": "avatar-owner",
                    "email": "owner@example.invalid",
                    "measurements_format": "Europe",
                    "image": SimpleUploadedFile("html.png", content()),
                },
                **kwargs,
            )
        return upload(client, **kwargs)

    return SimpleNamespace(**{"post" if html else "put": send})


@pytest.mark.django_db(transaction=True)
class TestImageConcurrency:
    @staticmethod
    def clients(owner, other=None):
        clients = [Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)]
        clients[0].force_login(owner)
        clients[1].force_login(other or owner)
        return clients, [csrf(client) for client in clients]

    @pytest.mark.parametrize("first_html", [None, True, False])
    def test_competing_api_and_html_uploads_leave_one_active_file(
        self, avatars, tmp_path, first_html
    ):
        clients, tokens = self.clients(avatars.owner)
        first = first_html is True
        second = first_html is False
        a, b = concurrent_changes(
            image_client(clients[0], html=first),
            (
                "post" if first else "put",
                reverse("profile") if first else reverse("api_v1:account-image"),
                tokens[0],
            ),
            image_client(clients[1], html=second),
            (
                "post" if second else "put",
                reverse("profile") if second else reverse("api_v1:account-image"),
                tokens[1],
            ),
        )
        assert a[0] in (200, 302) and b[0] in (200, 302)
        assert list(files(tmp_path)) == [current(avatars.owner).image.name]
        if first_html is not None:
            assert current(avatars.owner).measurements_format == "Europe"

    @pytest.mark.parametrize("delete_first", [True, False])
    def test_upload_and_reset_follow_owner_lock_order(self, avatars, tmp_path, delete_first):
        old_image(avatars.owner)
        clients, tokens = self.clients(avatars.owner)
        methods = ("delete", "put") if delete_first else ("put", "delete")
        bound = [
            clients[i] if method == "delete" else image_client(clients[i])
            for i, method in enumerate(methods)
        ]
        a, b = concurrent_changes(
            bound[0],
            (methods[0], reverse("api_v1:account-image"), tokens[0]),
            bound[1],
            (methods[1], reverse("api_v1:account-image"), tokens[1]),
        )
        assert a[0] in (200, 204) and b[0] in (200, 204)
        assert len(files(tmp_path)) == (1 if delete_first else 0)
        assert (current(avatars.owner).image.name == "default.jpg") is not delete_first

    def test_settings_update_preserves_new_image_and_other_accounts_are_independent(
        self, avatars, tmp_path
    ):
        clients, tokens = self.clients(avatars.owner)

        def settings_patch(target, *args, **kwargs):
            kwargs.pop("content_type", None)
            return clients[1].patch(
                target,
                '{"measurements_format":"Europe"}',
                content_type="application/json",
                **kwargs,
            )

        a, b = concurrent_changes(
            image_client(clients[0]),
            ("put", reverse("api_v1:account-image"), tokens[0]),
            SimpleNamespace(patch=settings_patch),
            ("patch", reverse("api_v1:account"), tokens[1]),
        )
        assert a[0] == b[0] == 200 and current(avatars.owner).measurements_format == "Europe"
        assert list(files(tmp_path)) == [current(avatars.owner).image.name]
        clients, tokens = self.clients(avatars.owner, avatars.other)
        a, b = concurrent_changes(
            image_client(clients[0]),
            ("put", reverse("api_v1:account-image"), tokens[0]),
            image_client(clients[1]),
            ("put", reverse("api_v1:account-image"), tokens[1]),
            same_user=False,
        )
        assert a[0] == b[0] == 200 and len(files(tmp_path)) == 2


def test_field_limited_user_save_cannot_restore_a_stale_cached_avatar(
    client, avatars, tmp_path, django_capture_on_commit_callbacks
):
    from django.utils import timezone

    stale = get_user_model().objects.get(pk=avatars.owner.pk)
    original = stale.profile.image.name
    with django_capture_on_commit_callbacks(execute=True):
        assert upload(client).status_code == 200
    active = current(avatars.owner).image.name
    assert active != original
    stale.last_login = timezone.now()
    stale.save(update_fields=["last_login"])
    assert current(avatars.owner).image.name == active
    assert list(files(tmp_path)) == [active]


@pytest.mark.django_db(transaction=True)
def test_html_username_race_cleans_staged_upload_even_when_error_is_rendered(
    client, avatars, tmp_path, monkeypatch
):
    from users.forms import UserUpdateForm

    old = old_image(avatars.owner)
    before_profile = Profile.objects.values().get(user=avatars.owner)
    before_user = get_user_model().objects.values().get(pk=avatars.owner.pk)
    before_files = files(tmp_path)
    original = UserUpdateForm.save

    def outsider():
        try:
            get_user_model().objects.create_user(
                username="avatar-external-race", email="external@example.invalid"
            )
        finally:
            connections.close_all()

    def collide(form, *args, **kwargs):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(outsider).result(timeout=10)
        return original(form, *args, **kwargs)

    monkeypatch.setattr(UserUpdateForm, "save", collide)
    response = client.post(
        reverse("profile"),
        {
            "username": "avatar-external-race",
            "email": "attempt@example.invalid",
            "measurements_format": "Europe",
            "image": SimpleUploadedFile("avatar.png", content()),
        },
    )
    assert response.status_code == 200 and "username" in response.context["u_form"].errors
    assert Profile.objects.values().get(user=avatars.owner) == before_profile
    assert get_user_model().objects.values().get(pk=avatars.owner.pk) == before_user
    assert files(tmp_path) == before_files
    assert response.context["p_form"].instance.image.name == old
