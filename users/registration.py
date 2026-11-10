"""Atomic web registration with the existing form's case-insensitive name policy."""

from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction

# Separate from loader/scheduler locks: two-int namespace "NHUR".
UNIQUE_VIOLATION_SQLSTATE = "23505"
REGISTRATION_LOCK_NAMESPACE = 0x4E485552
REGISTRATION_LOCK_SQL = "SELECT pg_advisory_xact_lock(%s, hashtext(UPPER(%s::text)))"


def create_registered_user(form):
    """Return the created user, or None with field errors on the supplied form.

    Both HTML and JSON callers pass an unvalidated registration form. PostgreSQL's
    UPPER matches the form's username__iexact lookup; hash collisions only serialize
    additional names. The lock and user/profile writes share a transaction.
    """
    try:
        username = form.fields["username"].clean(form.data.get("username", ""))
    except ValidationError:
        form.is_valid()
        return None
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(REGISTRATION_LOCK_SQL, [REGISTRATION_LOCK_NAMESPACE, username])
            if not form.is_valid():
                return None
            return form.save()
    except IntegrityError as error:
        # Writers outside these web flows may race the database unique constraint.
        # Convert only a proven username collision; unrelated failures still surface.
        model = form._meta.model
        if (
            username_constraint_violation(error, model)
            and model.objects.filter(username__iexact=username).exists()
        ):
            form.add_error("username", form.instance.unique_error_message(model, ["username"]))
            return None
        raise


def username_constraint_violation(error, model):
    cause = error.__cause__
    diagnostic = getattr(cause, "diag", None)
    if (
        getattr(cause, "pgcode", None) != UNIQUE_VIOLATION_SQLSTATE
        or getattr(diagnostic, "table_name", None) != model._meta.db_table
    ):
        return False
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
    constraint = constraints.get(diagnostic.constraint_name, {})
    return constraint.get("unique", False) and constraint.get("columns") == ["username"]
