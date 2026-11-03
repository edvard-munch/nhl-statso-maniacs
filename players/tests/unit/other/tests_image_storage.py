"""Repeated logo/photo loads retain the same filename and replace the saved bytes."""

import pytest
from django.core.files.base import ContentFile

from players.storage import OverwriteStorage


pytestmark = pytest.mark.unit


def test_loader_image_storage_replaces_an_existing_file_without_a_duplicate(tmp_path):
    storage = OverwriteStorage(location=str(tmp_path))
    name = "teams_logos/synthetic-team.svg"
    assert storage.save(name, ContentFile(b"original"), max_length=None) == name
    assert storage.save(name, ContentFile(b"refreshed"), max_length=None) == name
    with storage.open(name, "rb") as saved:
        assert saved.read() == b"refreshed"
    assert [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.svg")] == [name]
