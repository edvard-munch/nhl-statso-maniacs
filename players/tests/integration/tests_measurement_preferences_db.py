"""Saved measurement choices through real profile posts and rendered player data."""

from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
import pytest

from players import utils
from players.models import Goalie, Skater
from players.tests.integration.tests_players_season_table import ajax
from players.tests.unit.tests_readonly_db.conftest import no_live_http, view_data  # noqa: F401
from users.models import Profile


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def measurements(view_data, settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    monkeypatch.setattr(utils, "season_in_prog", lambda: False)
    owner = view_data["user"]
    owner.email = "measurements@example.invalid"
    owner.save(update_fields=["email"])
    other = User.objects.create_user(username="other-units-user", email="other@example.invalid")
    other.profile.measurements_format = "Europe"
    other.profile.save(update_fields=["measurements_format"])
    for key in ("skater", "goalie"):
        player = view_data[key]
        player.height, player.height_cm = "6 ft 0 in", 183
        player.weight, player.weight_kg = 200, 91
        player.save(update_fields=["height", "height_cm", "weight", "weight_kg"])
    return dict(view_data, other=other)


def preference_post(client, account, choice, **extra):
    payload = {"username": account.username, "email": account.email, **extra}
    if choice is not None:
        payload["measurements_format"] = choice
    return client.post(reverse("profile"), payload)


def player_snapshot():
    return {
        model.__name__: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie)
    }


@pytest.mark.parametrize("choice", ["Europe", "USA"])
def test_preference_saves_replays_and_only_updates_signed_in_account(client, measurements, choice):
    owner, other = measurements["user"], measurements["other"]
    owner.profile.measurements_format = "USA" if choice == "Europe" else "Europe"
    owner.profile.save(update_fields=["measurements_format"])
    other_before = Profile.objects.values().get(user=other)
    players_before = player_snapshot()
    client.force_login(owner)
    for _ in range(2):
        response = preference_post(
            client, owner, choice, user=other.pk, profile_id=other.profile.pk
        )
        assert response.status_code == 302
        assert response.url == reverse("profile")
        owner.refresh_from_db()
        assert owner.profile.measurements_format == choice
        form = client.get(reverse("profile"))
        assert form.context["ms_form"]["measurements_format"].value() == choice
    assert Profile.objects.values().get(user=other) == other_before
    assert player_snapshot() == players_before


@pytest.mark.parametrize("invalid", ["metric", "EUROPE", "", None])
def test_invalid_preference_preserves_profile_and_account_fields(client, measurements, invalid):
    owner = measurements["user"]
    owner.profile.measurements_format = "Europe"
    owner.profile.save(update_fields=["measurements_format"])
    client.force_login(owner)
    before_users = list(User.objects.order_by("pk").values())
    before_profiles = list(Profile.objects.order_by("pk").values())
    response = preference_post(
        client, owner, invalid, username="attempted-rename", email="attempted@example.invalid"
    )
    assert response.status_code == 200  # Browser profile form re-renders errors.
    assert "measurements_format" in response.context["ms_form"].errors
    assert list(User.objects.order_by("pk").values()) == before_users
    assert list(Profile.objects.order_by("pk").values()) == before_profiles


@pytest.mark.parametrize("method", ["get", "post"])
def test_profile_preference_requires_login(client, measurements, method):
    before = list(Profile.objects.order_by("pk").values())
    response = getattr(client, method)(reverse("profile"), {"measurements_format": "Europe"})
    assert response.status_code == 302
    redirect = urlsplit(response.url)
    assert redirect.path == reverse("login")
    next_url = reverse("profile") + ("?measurements_format=Europe" if method == "get" else "")
    assert parse_qs(redirect.query) == {"next": [next_url]}
    assert list(Profile.objects.order_by("pk").values()) == before


def test_preference_post_requires_csrf_and_preserves_values_without_token(measurements):
    owner = measurements["user"]
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(owner)
    strict.get(reverse("profile"))
    payload = {"username": owner.username, "email": owner.email, "measurements_format": "Europe"}
    assert strict.post(reverse("profile"), payload).status_code == 403
    assert Profile.objects.get(user=owner).measurements_format == "USA"
    token = strict.cookies["csrftoken"].value
    assert strict.post(reverse("profile"), payload, HTTP_X_CSRFTOKEN=token).status_code == 302
    assert Profile.objects.get(user=owner).measurements_format == "Europe"


@pytest.mark.parametrize("kind", ["skater", "goalie"])
@pytest.mark.parametrize("choice", ["anonymous", "USA", "Europe"])
def test_player_profile_displays_viewer_units_without_writing_player_values(
    client, measurements, kind, choice
):
    owner = measurements["user"]
    if choice != "anonymous":
        client.force_login(owner)
        assert preference_post(client, owner, choice).status_code == 302
    player = measurements[kind]
    before = player_snapshot()
    response = client.get(reverse("player_detail", args=[player.slug, player.nhl_id]))
    assert response.status_code == 200
    height, weight = (183, 91) if choice == "Europe" else ("6 ft 0 in", 200)
    assert response.context["player"].height == height
    assert response.context["player"].weight == weight
    assert f"<b>Height:</b> {height}".encode() in response.content
    assert f"<b>Weight:</b> {weight}".encode() in response.content
    assert player_snapshot() == before


@pytest.mark.parametrize("mode", ["tot", "avg", "gls"])
@pytest.mark.parametrize("choice", ["USA", "Europe"])
def test_saved_preference_controls_player_table_units_and_height_options(
    client, measurements, mode, choice
):
    owner = measurements["user"]
    client.force_login(owner)
    assert preference_post(client, owner, choice).status_code == 302
    player = measurements["goalie" if mode == "gls" else "skater"]
    before = player_snapshot()
    response = ajax(client, stat_type=mode, filters="fcol[2]=" + player.name)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    row = data["rows"][0]
    assert (row[6], row[7]) == ((183, 91) if choice == "Europe" else ("6 ft 0 in", 200))
    assert data["height_values"] == ([183] if choice == "Europe" else {"183": "6 ft 0 in"})
    assert player_snapshot() == before


def test_switching_viewers_and_preferences_has_no_unit_leak_or_conversion_drift(
    client, measurements
):
    owner, other = measurements["user"], measurements["other"]
    player = measurements["skater"]
    before = player_snapshot()
    for viewer, choice in [(owner, "Europe"), (other, "USA"), (owner, "USA"), (other, "Europe")]:
        client.force_login(viewer)
        assert preference_post(client, viewer, choice).status_code == 302
        response = client.get(reverse("player_detail", args=[player.slug, player.nhl_id]))
        assert response.context["player"].weight == (91 if choice == "Europe" else 200)
        table = ajax(client, filters="fcol[2]=" + player.name).json()
        assert table["rows"][0][7] == (91 if choice == "Europe" else 200)
    assert player_snapshot() == before
    assert Profile.objects.get(user=owner).measurements_format == "USA"
    assert Profile.objects.get(user=other).measurements_format == "Europe"
