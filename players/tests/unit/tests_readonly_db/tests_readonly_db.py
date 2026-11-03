"""Lookup contracts independent of any developer's NHL records."""

import pytest
from players import utils

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("key", ["skater", "goalie", "second_goalie"])
def test_get_player_finds_exact_identity_and_team(view_data, key):
    expected = view_data[key]
    actual = utils.get_player(expected.nhl_id, expected.slug)
    assert type(actual) is type(expected)
    assert actual.pk == expected.pk
    assert actual.name == expected.name
    assert actual.team_id == view_data["home"].pk


@pytest.mark.parametrize("key", ["skater", "goalie"])
def test_get_player_does_not_accept_wrong_slug(view_data, key):
    assert utils.get_player(view_data[key].nhl_id, "wrong-slug") is None


def test_get_player_returns_none_for_unknown_identity(view_data):
    assert utils.get_player(9999999, "missing-player") is None
