from players import utils
import pytest


@pytest.mark.django_db()
@pytest.mark.parametrize('id, slug, name', [
    [8480021, 'jack-studnicka', 'Jack Studnicka'],
    [8478499, 'adin-hill', 'Adin Hill'],
    [8471239, 'cory-schneider', 'Cory Schneider'],
])
def test_get_player(id, slug, name):
    player = utils.get_player(id, slug)

    assert player
    assert player.name == name
    # assert utils.get_player(849, 'adin-hill') == None
