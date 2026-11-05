"""Private note/position ownership, validation and persistence contracts."""

from types import SimpleNamespace

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
import pytest

from players import utils
from players.models import Goalie, Note, Position, Skater


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock, monkeypatch):
    monkeypatch.setattr(utils, "season_in_prog", lambda: False)


@pytest.fixture
def owned(client):
    owner = User.objects.create_user(username="owned-data-owner")
    other = User.objects.create_user(username="owned-data-other")
    common = dict(pk=101, birth_date="2000-01-01", games=1, sbs_stats=[], career_stats={})
    skater = Skater.objects.create(
        nhl_id=900001, name="Private Skater", position_abbr="C", sbs_stats_avg=[], **common
    )
    goalie = Goalie.objects.create(
        nhl_id=900002, name="Private Goalie", position_abbr="G", **common
    )
    client.force_login(owner)
    return SimpleNamespace(owner=owner, other=other, skater=skater, goalie=goalie)


def endpoint(player, route):
    return reverse(route, args=[player.slug, player.nhl_id])


@pytest.mark.parametrize(
    "route,model,payload",
    [
        ("player_note", Note, {"text": "private note"}),
        ("player_positions", Position, {"check": ["C", "LW"]}),
    ],
)
def test_shared_player_pk_and_other_users_remain_separate(client, owned, route, model, payload):
    assert owned.skater.pk == owned.goalie.pk
    for player in (owned.skater, owned.goalie):
        result = client.post(endpoint(player, route), payload)
        assert result.status_code == 200
        record = model.objects.get(
            author=owned.owner,
            object_id=player.pk,
            content_type=ContentType.objects.get_for_model(player),
        )
        assert record.content_object == player
        assert record.player_name == player.name
    client.force_login(owned.other)
    assert client.post(endpoint(owned.skater, route), payload).status_code == 200
    assert model.objects.count() == 3
    # Untrusted author/object parameters must not select another user's row.
    update = {**payload, "author": owned.owner.pk, "object_id": owned.goalie.pk}
    if route == "player_note":
        update["text"] = "other user's edit"
    else:
        update["check"] = ["D"]
    client.post(endpoint(owned.skater, route), update)
    original = model.objects.get(
        author=owned.owner, content_type=ContentType.objects.get_for_model(owned.skater)
    )
    assert (original.text if route == "player_note" else original.data) == (
        "private note" if route == "player_note" else ["C", "LW"]
    )
    client.force_login(owned.owner)
    client.post(endpoint(owned.skater, route), {"text": ""} if route == "player_note" else {})
    assert model.objects.count() == 2
    assert model.objects.filter(
        author=owned.owner, content_type=ContentType.objects.get_for_model(owned.goalie)
    ).exists()


@pytest.mark.parametrize(
    "route,model,payload",
    [
        ("player_note", Note, {"text": "  first note  "}),
        ("player_positions", Position, {"check": ["C", "LW"]}),
    ],
)
def test_repeat_update_and_clear_are_idempotent(client, owned, route, model, payload):
    url = endpoint(owned.skater, route)
    first = client.post(url, payload)
    assert first.status_code == 200
    record = model.objects.get()
    if route == "player_note":
        assert record.text == "first note"
        payload = {"text": "updated"}
    else:
        assert first.json()["ajax_upd_pos"] == "C, LW"
        payload = {"check": ["D", "RW"]}
    for _ in range(2):
        assert client.post(url, payload).status_code == 200
    assert model.objects.get().pk == record.pk
    clear = {"text": " \t "} if route == "player_note" else {}
    for _ in range(2):
        response = client.post(url, clear)
        assert response.status_code == 200
        assert model.objects.count() == 0
        if route == "player_positions":
            assert response.json()["ajax_upd_pos"] == "C"


@pytest.mark.parametrize("bad", [["INVALID"], ["<img>"], ["G"], ["C", "BAD"]])
def test_invalid_positions_return_400_and_preserve_existing_record(client, owned, bad):
    url = endpoint(owned.skater, "player_positions")
    client.post(url, {"check": ["C", "LW"]})
    before = list(Position.objects.values())
    response = client.post(url, {"check": bad})
    assert response.status_code == 400
    assert "errors" in response.json()
    assert list(Position.objects.values()) == before


def test_note_length_boundary_and_validation_error_preserve_data(client, owned):
    url = endpoint(owned.skater, "player_note")
    assert client.post(url, {"text": "x" * 400}).status_code == 200
    before = list(Note.objects.values())
    response = client.post(url, {"text": "x" * 401})
    assert response.status_code == 400
    assert "text" in response.json()["errors"]
    assert list(Note.objects.values()) == before


@pytest.mark.parametrize("route", ["player_note", "player_positions"])
def test_missing_player_is_404_without_creating_private_data(client, owned, route):
    response = client.post(
        reverse(route, args=["missing", 999999]), {"text": "note", "check": ["C"]}
    )
    assert response.status_code == 404
    assert Note.objects.count() == Position.objects.count() == 0


@pytest.mark.parametrize("route", ["player_note", "player_positions"])
def test_anonymous_posts_cannot_create_private_data(client, owned, route):
    client.logout()
    response = client.post(endpoint(owned.skater, route), {"text": "note", "check": ["C"]})
    assert response.status_code == 200  # Preserve existing anonymous AJAX contract.
    assert response.json()["authenticated"] is False
    assert Note.objects.count() == Position.objects.count() == 0


def test_profile_reads_only_viewers_notes_and_escapes_note_text(client, owned):
    attack = '</textarea><script>alert("private")</script>'
    client.post(endpoint(owned.skater, "player_note"), {"text": attack})
    client.post(endpoint(owned.goalie, "player_note"), {"text": "goalie-only secret"})
    response = client.get(endpoint(owned.skater, "player_detail"))
    assert response.context["note"].text == attack
    assert attack.encode() not in response.content
    assert b"goalie-only secret" not in response.content
    assert b"&lt;/textarea&gt;" in response.content
    client.force_login(owned.other)
    response = client.get(endpoint(owned.skater, "player_detail"))
    assert response.context["note"] is None
    assert b"alert(&quot;private&quot;)" not in response.content


@pytest.mark.parametrize(
    "route,model,fields",
    [("player_note", Note, {"text": "legacy"}), ("player_positions", Position, {"data": ["LW"]})],
)
def test_ambiguous_untyped_legacy_rows_are_preserved_and_never_exposed(
    client, owned, route, model, fields
):
    legacy = model.objects.create(
        author=owned.owner, object_id=owned.skater.pk, player_name="Ambiguous legacy", **fields
    )
    response = client.get(endpoint(owned.skater, "player_detail"))
    assert response.context["note" if route == "player_note" else "positions"] == (
        None if route == "player_note" else "C"
    )
    client.post(endpoint(owned.skater, route), {"text": "new typed note", "check": ["D"]})
    legacy.refresh_from_db()
    assert legacy.content_type_id is None
    assert (legacy.text if route == "player_note" else legacy.data) == (
        "legacy" if route == "player_note" else ["LW"]
    )
    assert model.objects.count() == 2


@pytest.mark.parametrize(
    "route,model,fields",
    [("player_note", Note, {"text": "legacy"}), ("player_positions", Position, {"data": ["LW"]})],
)
def test_unambiguous_legacy_rows_are_read_and_upgraded_on_edit(client, owned, route, model, fields):
    owned.goalie.delete()
    legacy = model.objects.create(
        author=owned.owner, object_id=owned.skater.pk, player_name=owned.skater.name, **fields
    )
    profile = client.get(endpoint(owned.skater, "player_detail"))
    assert profile.context["note" if route == "player_note" else "positions"] == (
        legacy if route == "player_note" else "LW"
    )
    client.post(endpoint(owned.skater, route), {"text": "updated legacy", "check": ["D"]})
    legacy.refresh_from_db()
    assert legacy.content_object == owned.skater
    assert model.objects.count() == 1


@pytest.mark.parametrize(
    "route,payload",
    [("player_note", {"text": "csrf protected"}), ("player_positions", {"check": ["LW"]})],
)
def test_private_posts_require_csrf_token(owned, route, payload):
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(owned.owner)
    strict.get(endpoint(owned.skater, "player_detail"))
    assert strict.post(endpoint(owned.skater, route), payload).status_code == 403
    token = strict.cookies["csrftoken"].value
    assert (
        strict.post(endpoint(owned.skater, route), payload, HTTP_X_CSRFTOKEN=token).status_code
        == 200
    )
