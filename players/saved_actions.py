"""Serialize saved-list changes for one account across requests and workers."""

from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.db import transaction


@contextmanager
def locked_user(user):
    # Membership rows may not exist yet, and favorites span two M2M tables.
    # Every toggle/reset must lock this same existing row before reading lists.
    with transaction.atomic():
        owner = get_user_model().objects.select_for_update().get(pk=user.pk)
        yield owner
