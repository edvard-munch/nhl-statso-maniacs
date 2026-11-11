"""Typed private player records; callers serialize writes with saved_actions.locked_user."""

from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType

from .models import Goalie, Skater, Note

NONE = "none"
TYPED = "typed"
LEGACY = "legacy"
AMBIGUOUS = "ambiguous"
INVALID = "invalid"
SOURCES = (NONE, TYPED, LEGACY, AMBIGUOUS, INVALID)
DUPLICATE_CHECK_LIMIT = 2


class OwnedDataConflict(Exception):
    """Multiple typed records cannot be safely edited or selected automatically."""


@dataclass(frozen=True)
class Selection:
    record: object = None
    source: str = NONE
    typed_conflict: bool = False


def lookup(owner, player, model):
    records = model.objects.filter(author_id=owner.pk, object_id=player.pk)
    content_type = ContentType.objects.get_for_model(player)
    typed = list(records.filter(content_type=content_type).order_by("pk")[:DUPLICATE_CHECK_LIMIT])
    if len(typed) == DUPLICATE_CHECK_LIMIT:
        return Selection(source=AMBIGUOUS, typed_conflict=True)
    if typed:
        return Selection(typed[0], TYPED)
    legacy = list(records.filter(content_type__isnull=True).order_by("pk")[:DUPLICATE_CHECK_LIMIT])
    if not legacy:
        return Selection()
    other_model = Goalie if isinstance(player, Skater) else Skater
    if len(legacy) == DUPLICATE_CHECK_LIMIT or other_model.objects.filter(pk=player.pk).exists():
        return Selection(source=AMBIGUOUS)
    return Selection(legacy[0], LEGACY)


def replace(owner, player, model, value):
    """Validated explicit replacement; ambiguous untyped records remain untouched."""
    selection = lookup(owner, player, model)
    if selection.typed_conflict:
        raise OwnedDataConflict()
    if value:
        record = selection.record if selection.record is not None else model(author=owner)
        setattr(record, "text" if model is Note else "data", value)
        record.player_name = player.name
        record.content_object = player
        record.save()
    else:
        if selection.record is not None:
            selection.record.delete()
            # Clearing a typed row must not reveal an older, safely attributable
            # legacy value on the next read. Ambiguous legacy rows are preserved.
            remaining = lookup(owner, player, model)
            if remaining.source == LEGACY:
                remaining.record.delete()
