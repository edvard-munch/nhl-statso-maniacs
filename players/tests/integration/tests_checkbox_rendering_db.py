"""AJAX filter values round-trip through escaped checkbox attributes unchanged."""

from copy import deepcopy
import json

import pytest

from players import utils
from players.models import Skater, Team
from players.tests.integration.tests_players_season_table import ajax, table_players  # noqa: F401
from players.tests.unit.other.tests_checkbox_rendering import Checkboxes

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("family", ["teams", "nations", "positions"])
@pytest.mark.parametrize("mode", ["tot", "avg"])
def test_checkbox_ajax_round_trip_preserves_literal_values_and_selection(
    client, table_players, family, mode, requests_mock
):
    value = 'A&B "><img src=x onerror=alert(1)>'
    tooltip = '<script>Literal & "tooltip"</script>'
    player = table_players["low"]
    if family == "teams":
        Team.objects.create(nhl_id=99, abbr=value, name=tooltip)
        rows = deepcopy(player.sbs_stats)
        for row in rows:
            row["teamAbbr"] = value
        player.sbs_stats = rows
        player.save(update_fields=["sbs_stats"])
    elif family == "nations":
        player.nation = value
        player.save(update_fields=["nation"])
    else:
        player.position_abbr = value
        player.position_name = tooltip
        player.save(update_fields=["position_abbr", "position_name"])
    before = {model: list(model.objects.order_by("pk").values()) for model in (Skater, Team)}
    response = ajax(client, stat_type=mode)
    assert response.status_code == 200
    assert response.json()["total"] == 2
    controls = Checkboxes(response.json()["all_" + family])
    option = next(item for item in controls.inputs if item["value"] == value)
    assert set(option) == {"type", "class", "value", "id"}
    assert option["id"] == value
    label = next(item for item in controls.labels if item["attrs"]["for"] == value)
    assert label["text"] == value + " " + (tooltip if family != "nations" else "")
    # Use the decoded HTML value as a browser would, rather than an HTML entity string.
    selected = {family: [option["value"]]}
    response = ajax(client, stat_type=mode, checkboxes="checkbox_filter=" + json.dumps(selected))
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "Current Low" in data["rows"][0][utils.COLUMNS.index("name")]
    controls = Checkboxes(data["all_" + family])
    assert [item["value"] for item in controls.inputs if "checked" in item] == [value]
    response = ajax(
        client, stat_type=mode, checkboxes="checkbox_filter=" + json.dumps({family: []})
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert all(
        "checked" not in item for item in Checkboxes(response.json()["all_" + family]).inputs
    )
    assert {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Team)
    } == before
