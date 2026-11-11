"""Private typed note/position resources, safe legacy attribution and shared writer races."""

import json
from types import SimpleNamespace

from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
import pytest

from players.models import Note, Position, Skater
from players.tests.integration.tests_owned_player_data_db import owned  # noqa: F401
from players.tests.integration.tests_favorites_api_db import concurrent_changes, csrf

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

RESOURCES = [
    ("note", Note, "text", "private note"),
    ("positions", Position, "positions", ["C", "LW"]),
]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


def url(resource="note", player_type="skater", nhl_id=900001):
    return reverse("api_v1:player-" + resource, args=[player_type, nhl_id])


def put(client, resource, payload, player_type="skater", nhl_id=900001, **headers):
    return client.put(
        url(resource, player_type, nhl_id),
        json.dumps(payload),
        content_type="application/json",
        **headers,
    )


def records():
    return {model: list(model.objects.order_by("pk").values()) for model in (Note, Position)}


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_read_replace_repeat_and_clear_preserve_typed_identity_and_official_fields(
    client, owned, resource, model, field, value
):
    before = Skater.objects.values().get(pk=owned.skater.pk)
    empty = client.get(url(resource)).json()
    assert empty["source"] == "none" and empty[field] is None
    for _ in range(2):
        response = put(client, resource, {field: value})
        assert response.status_code == 200 and response.json()[field] == value
        assert response.json()["source"] == "typed"
    assert model.objects.count() == 1
    record = model.objects.get()
    assert record.content_object == owned.skater and record.author == owned.owner
    assert record.player_name == owned.skater.name
    assert Skater.objects.values().get(pk=owned.skater.pk) == before
    if resource == "positions":
        assert response.json()["official_position"] == "C"
        assert response.json()["effective_positions"] == value
    for _ in range(2):
        cleared = client.delete(url(resource))
        assert cleared.status_code == 204 and cleared.content == b""
    assert model.objects.count() == 0 and client.get(url(resource)).json()[field] is None


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_other_accounts_and_same_pk_or_nhl_id_in_other_player_model_are_isolated(
    client, owned, resource, model, field, value
):
    assert owned.skater.pk == owned.goalie.pk
    owned.goalie.nhl_id = owned.skater.nhl_id
    owned.goalie.save(update_fields=["nhl_id"])
    assert put(client, resource, {field: value}).status_code == 200
    assert put(client, resource, {field: value}, "goalie", owned.goalie.nhl_id).status_code == 200
    client.force_login(owned.other)
    assert client.get(url(resource)).json()[field] is None
    assert put(client, resource, {field: value}).status_code == 200
    assert model.objects.count() == 3
    client.force_login(owned.owner)
    assert client.delete(url(resource)).status_code == 204
    assert model.objects.count() == 2
    assert client.get(url(resource, "goalie", owned.goalie.nhl_id)).json()[field] == value


def test_note_matches_form_trim_length_and_stays_plain_text(client, owned):
    text = '</textarea><script>alert("private")</script>'
    response = put(client, "note", {"text": "  " + text + "  "})
    assert response.json()["text"] == text
    assert put(client, "note", {"text": " " + "x" * 400 + " "}).status_code == 200
    before = records()
    response = put(client, "note", {"text": "x" * 401})
    assert response.status_code == 400 and "text" in response.json()["error"]["fields"]
    assert records() == before
    assert put(client, "note", {"text": " \t "}).json()["text"] is None
    assert Note.objects.count() == 0


def test_position_choices_duplicate_normalization_and_clear_match_legacy(client, owned):
    response = put(client, "positions", {"positions": ["D", "RW", "D"]})
    assert response.json()["positions"] == ["D", "RW"]
    assert response.json()["effective_positions"] == ["D", "RW"]
    assert put(client, "positions", {"positions": []}).json()["positions"] is None
    assert client.get(url("positions")).json()["effective_positions"] == ["C"]
    goalie = put(client, "positions", {"positions": ["D"]}, "goalie", owned.goalie.nhl_id)
    assert goalie.status_code == 200  # Existing form policy supports both player models.
    assert client.delete(url("positions", "goalie", owned.goalie.nhl_id)).status_code == 204
    assert client.get(url("positions", "goalie", owned.goalie.nhl_id)).json()[
        "effective_positions"
    ] == ["G"]
    Skater.objects.filter(pk=owned.skater.pk).update(position_abbr="")
    assert client.get(url("positions")).json()["effective_positions"] == []


@pytest.mark.parametrize(
    "resource,payload",
    [
        ("note", {}),
        ("note", {"text": None}),
        ("note", {"text": False}),
        ("note", {"text": 123}),
        ("note", {"text": []}),
        ("note", {"text": "bad\u0000note"}),
        ("note", []),
        ("note", {"text": "x", "author": 1}),
        ("note", {"text": "x", "content_type": 1}),
        ("positions", {}),
        ("positions", {"positions": None}),
        ("positions", {"positions": "C"}),
        ("positions", {"positions": ["G"]}),
        ("positions", {"positions": ["L"]}),
        ("positions", {"positions": ["C", "BAD"]}),
        ("positions", {"positions": [1]}),
        ("positions", {"positions": ["C"], "object_id": 1}),
    ],
)
def test_invalid_or_injected_payloads_are_400_and_preserve_existing_values(
    client, owned, resource, payload
):
    put(client, "note", {"text": "existing"})
    put(client, "positions", {"positions": ["LW"]})
    before = records()
    assert put(client, resource, payload).status_code == 400
    assert records() == before


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_private_reads_are_read_only_and_public_json_excludes_private_state(
    client, owned, resource, model, field, value, offline, django_assert_num_queries
):
    put(client, resource, {field: value})
    ContentType.objects.get_for_model(owned.skater)
    before = records()
    with django_assert_num_queries(7):
        response = client.get(url(resource))
    assert response.status_code == 200
    assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
    assert "cookie" in response["Vary"].lower() and response["X-Request-ID"]
    assert records() == before and not offline.called
    public = client.get(
        reverse("api_v1:player-detail", args=["skater", owned.skater.nhl_id])
    ).json()
    assert public["player"]["position_abbr"] == "C"
    assert "private note" not in str(public)
    assert not {"note", "positions", "effective_positions", "author"}.intersection(public["player"])
    assert client.head(url(resource)).status_code == 200


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_no_saved_membership_is_required_and_legacy_editor_reads_api_records(
    client, owned, resource, model, field, value
):
    assert not owned.skater.favoriting.exists() and not owned.skater.comparing.exists()
    put(client, resource, {field: value})
    route = "player_note" if resource == "note" else "player_positions"
    body = {"text": "legacy edit"} if resource == "note" else {"check": ["D"]}
    assert (
        client.post(reverse(route, args=[owned.skater.slug, owned.skater.nhl_id]), body).status_code
        == 200
    )
    data = client.get(url(resource)).json()
    assert data[field] == ("legacy edit" if resource == "note" else ["D"])
    assert model.objects.count() == 1


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_ambiguous_untyped_records_are_never_exposed_guessed_or_deleted(
    client, owned, resource, model, field, value
):
    kwargs = {"text": "ambiguous secret"} if resource == "note" else {"data": ["RW"]}
    legacy = model.objects.create(
        author=owned.owner, object_id=owned.skater.pk, player_name="Ambiguous", **kwargs
    )
    original = model.objects.values().get(pk=legacy.pk)
    data = client.get(url(resource)).json()
    assert data["source"] == "ambiguous" and data[field] is None
    assert client.delete(url(resource)).status_code == 204
    assert model.objects.values().get(pk=legacy.pk) == original
    assert put(client, resource, {field: value}).json()["source"] == "typed"
    assert client.delete(url(resource)).status_code == 204
    assert model.objects.values().get(pk=legacy.pk) == original
    assert client.get(url(resource)).json()["source"] == "ambiguous"


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_single_unambiguous_legacy_record_reads_without_writes_and_upgrades_on_edit(
    client, owned, resource, model, field, value
):
    owned.goalie.delete()
    kwargs = {"text": value} if resource == "note" else {"data": value}
    legacy = model.objects.create(
        author=owned.owner, object_id=owned.skater.pk, player_name=owned.skater.name, **kwargs
    )
    before = records()
    data = client.get(url(resource)).json()
    assert data["source"] == "legacy" and data[field] == value
    assert records() == before
    assert put(client, resource, {field: value}).json()["source"] == "typed"
    legacy.refresh_from_db()
    assert legacy.content_object == owned.skater and model.objects.count() == 1


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_clear_does_not_resurrect_safely_attributable_shadowed_legacy_data(
    client, owned, resource, model, field, value
):
    owned.goalie.delete()
    kwargs = {"text": value} if resource == "note" else {"data": value}
    model.objects.create(
        author=owned.owner, object_id=owned.skater.pk, player_name=owned.skater.name, **kwargs
    )
    model.objects.create(
        author=owned.owner, content_object=owned.skater, player_name=owned.skater.name, **kwargs
    )
    assert model.objects.count() == 2
    assert client.delete(url(resource)).status_code == 204
    assert model.objects.count() == 0 and client.get(url(resource)).json()[field] is None


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_duplicate_typed_rows_are_hidden_and_conflict_instead_of_guessing(
    client, owned, resource, model, field, value
):
    kwargs = {"text": value} if resource == "note" else {"data": value}
    for _ in range(2):
        model.objects.create(
            author=owned.owner, content_object=owned.skater, player_name=owned.skater.name, **kwargs
        )
    before = records()
    data = client.get(url(resource)).json()
    assert data["source"] == "ambiguous" and data[field] is None
    for response in [put(client, resource, {field: value}), client.delete(url(resource))]:
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "private_player_data_conflict"
        )
    route = "player_note" if resource == "note" else "player_positions"
    body = {"text": "edit"} if resource == "note" else {"check": ["D"]}
    assert (
        client.post(reverse(route, args=[owned.skater.slug, owned.skater.nhl_id]), body).status_code
        == 409
    )
    assert records() == before


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_duplicate_untyped_rows_remain_ambiguous_even_when_one_player_type_exists(
    client, owned, resource, model, field, value
):
    owned.goalie.delete()
    kwargs = {"text": value} if resource == "note" else {"data": value}
    for _ in range(2):
        model.objects.create(
            author=owned.owner, object_id=owned.skater.pk, player_name="legacy", **kwargs
        )
    assert client.get(url(resource)).json()["source"] == "ambiguous"
    assert put(client, resource, {field: value}).status_code == 200
    assert model.objects.count() == 3
    assert client.delete(url(resource)).status_code == 204
    assert model.objects.count() == 2 and client.get(url(resource)).json()[field] is None


@pytest.mark.parametrize("raw", [["G"], [], [None], ["BAD", "C"]])
def test_invalid_stored_override_is_not_reinterpreted_and_can_be_replaced(client, owned, raw):
    record = Position.objects.create(
        author=owned.owner, content_object=owned.skater, player_name=owned.skater.name, data=raw
    )
    data = client.get(url("positions")).json()
    assert (
        data["source"] == "invalid"
        and data["positions"] is None
        and data["effective_positions"] == ["C"]
    )
    record.refresh_from_db()
    assert record.data == raw
    assert put(client, "positions", {"positions": ["LW"]}).json()["source"] == "typed"
    assert Position.objects.count() == 1


@pytest.mark.parametrize("resource", ["note", "positions"])
@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_anonymous_requests_require_authentication(client, owned, resource, method):
    client.logout()
    response = getattr(client, method)(url(resource))
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "authentication_required"
    )
    assert records() == {Note: [], Position: []}


@pytest.mark.parametrize("resource", ["note", "positions"])
@pytest.mark.parametrize(
    "target", [("invalid", 900001), ("skater", 0), ("goalie", 2**31), ("skater", 999999)]
)
def test_invalid_or_unknown_targets_are_404_without_writes(client, owned, resource, target):
    assert client.get(url(resource, *target)).status_code == 404
    assert client.delete(url(resource, *target)).status_code == 404
    field, value = ("text", "note") if resource == "note" else ("positions", ["C"])
    assert put(client, resource, {field: value}, *target).status_code == 404
    assert records() == {Note: [], Position: []}


@pytest.mark.parametrize("resource", ["note", "positions"])
@pytest.mark.parametrize("storage", ["cookie", "http_only", "session"])
def test_put_and_delete_require_csrf_under_all_supported_storage_modes(
    owned, settings, resource, storage
):
    settings.CSRF_USE_SESSIONS = storage == "session"
    settings.CSRF_COOKIE_HTTPONLY = storage == "http_only"
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(owned.owner)
    payload = {"text": "secret"} if resource == "note" else {"positions": ["LW"]}
    assert put(strict, resource, payload).status_code == 403
    token = csrf(strict)
    assert put(strict, resource, payload, HTTP_X_CSRFTOKEN=token).status_code == 200
    assert strict.delete(url(resource)).status_code == 403
    assert (
        strict.delete(
            url(resource), HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://untrusted.invalid"
        ).status_code
        == 403
    )
    assert strict.delete(url(resource), HTTP_X_CSRFTOKEN=token).status_code == 204


@pytest.mark.parametrize("resource", ["note", "positions"])
def test_wire_format_methods_and_queries_are_explicit(client, owned, resource):
    field, value = ("text", "secret") if resource == "note" else ("positions", ["D"])
    for method in ("post", "patch"):
        assert getattr(client, method)(url(resource)).status_code == 405
    assert client.put(url(resource), {field: value}).status_code == 415
    assert client.put(url(resource), "{bad", content_type="application/json").status_code == 400
    assert (
        client.put(
            url(resource) + "?owner=1", json.dumps({field: value}), content_type="application/json"
        ).status_code
        == 400
    )
    assert client.get(url(resource), {"season_id": "20262027"}).status_code == 400
    assert (
        client.delete(
            url(resource), json.dumps({"clear": True}), content_type="application/json"
        ).status_code
        == 400
    )
    assert client.delete(url(resource), "{}", content_type="application/json").status_code == 204


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_response_failure_rolls_back_new_or_updated_records(
    client, owned, monkeypatch, resource, model, field, value
):
    serializer = "PrivateNoteSerializer" if resource == "note" else "PrivatePositionsSerializer"

    def fail(*args):
        raise RuntimeError("synthetic serialization failure")

    client.raise_request_exception = False
    monkeypatch.setattr("players.api.owned_player_data." + serializer + ".to_representation", fail)
    assert put(client, resource, {field: value}).status_code == 500
    assert model.objects.count() == 0
    kwargs = {"text": "original"} if resource == "note" else {"data": ["D"]}
    model.objects.create(
        author=owned.owner, content_object=owned.skater, player_name=owned.skater.name, **kwargs
    )
    before = records()
    assert put(client, resource, {field: value}).status_code == 500
    assert records() == before


@pytest.mark.parametrize("resource,model,field,value", RESOURCES)
def test_delete_failure_rolls_back_removal(
    client, owned, monkeypatch, resource, model, field, value
):
    from players import owned_data

    put(client, resource, {field: value})
    before = records()
    original = owned_data.replace

    def fail(*args):
        original(*args)
        raise RuntimeError("synthetic delete failure")

    monkeypatch.setattr(owned_data, "replace", fail)
    client.raise_request_exception = False
    assert client.delete(url(resource)).status_code == 500
    assert records() == before


def test_schema_private_put_delete_and_nullable_source_fields(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    for resource in ("note", "positions"):
        operations = schema["paths"]["/api/v1/me/players/{player_type}/{nhl_id}/" + resource + "/"]
        assert set(operations) == {"get", "put", "delete"}
        for method in operations:
            assert operations[method]["security"] == [{"cookieAuth": []}]
        assert "409" in operations["put"]["responses"]
        assert "content" not in operations["delete"]["responses"]["204"]
    assert schema["components"]["schemas"]["PrivateNote"]["properties"]["text"]["nullable"]


def with_payload(client, method, payload):
    def send(target, *args, **kwargs):
        kwargs.pop("content_type", None)
        if method == "put":
            return client.put(
                target, json.dumps(payload), content_type="application/json", **kwargs
            )
        return client.post(target, payload, **kwargs)

    return SimpleNamespace(**{method: send})


@pytest.mark.django_db(transaction=True)
class TestPrivatePlayerConcurrency:
    @staticmethod
    def clients(owner, other=None):
        clients = [Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)]
        clients[0].force_login(owner)
        clients[1].force_login(other or owner)
        return clients, [csrf(client) for client in clients]

    @pytest.mark.parametrize("resource,model,field,value", RESOURCES)
    @pytest.mark.parametrize("first_legacy", [None, True, False])
    def test_concurrent_creates_do_not_duplicate_and_share_legacy_lock(
        self, owned, resource, model, field, value, first_legacy
    ):
        clients, tokens = self.clients(owned.owner)
        second_value = "second" if resource == "note" else ["D"]
        route = "player_note" if resource == "note" else "player_positions"
        requests = []
        bound = []
        for index, current in enumerate((value, second_value)):
            legacy = (
                (index == 0 if first_legacy else index == 1) if first_legacy is not None else False
            )
            method = "post" if legacy else "put"
            payload = (
                {"text": current}
                if resource == "note"
                else {"check" if legacy else "positions": current}
            )
            target = (
                reverse(route, args=[owned.skater.slug, owned.skater.nhl_id])
                if legacy
                else url(resource)
            )
            bound.append(with_payload(clients[index], method, payload))
            requests.append((method, target, tokens[index]))
        a, b = concurrent_changes(bound[0], requests[0], bound[1], requests[1])
        assert (a[0], b[0]) == (200, 200)
        assert model.objects.count() == 1
        record = model.objects.get()
        assert (record.text if resource == "note" else record.data) == second_value

    @pytest.mark.parametrize("resource,model,field,value", RESOURCES)
    @pytest.mark.parametrize("clear_first", [True, False])
    def test_replacement_and_clear_follow_lock_order(
        self, owned, resource, model, field, value, clear_first
    ):
        clients, tokens = self.clients(owned.owner)
        methods = ("delete", "put") if clear_first else ("put", "delete")
        bound = [
            with_payload(clients[i], method, {field: value}) if method == "put" else clients[i]
            for i, method in enumerate(methods)
        ]
        a, b = concurrent_changes(
            bound[0],
            (methods[0], url(resource), tokens[0]),
            bound[1],
            (methods[1], url(resource), tokens[1]),
        )
        assert a[0] in (200, 204) and b[0] in (200, 204)
        assert model.objects.count() == (1 if clear_first else 0)

    @pytest.mark.parametrize("resource,model,field,value", RESOURCES)
    def test_read_waits_for_update_and_other_owners_are_independent(
        self, owned, resource, model, field, value
    ):
        clients, tokens = self.clients(owned.owner)
        a, b = concurrent_changes(
            with_payload(clients[0], "put", {field: value}),
            ("put", url(resource), tokens[0]),
            clients[1],
            ("get", url(resource), tokens[1]),
        )
        assert a[0] == b[0] == 200 and b[1][field] == value
        clients, tokens = self.clients(owned.owner, owned.other)
        a, b = concurrent_changes(
            with_payload(clients[0], "put", {field: value}),
            ("put", url(resource), tokens[0]),
            with_payload(clients[1], "put", {field: value}),
            ("put", url(resource), tokens[1]),
            same_user=False,
        )
        assert a[0] == b[0] == 200 and model.objects.count() == 2
