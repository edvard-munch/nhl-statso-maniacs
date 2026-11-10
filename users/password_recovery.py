"""Trusted plain-text reset mail and atomic Django-token consumption."""

import logging
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import URLValidator
from django.db import connection, transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

logger = logging.getLogger(__name__)
EXPECTED_MAIL_COUNT = 1
PASSWORD_RESET_SUBJECT = "Reset your NHL Web App password"
MAX_RESET_UID_LENGTH = 128
MAX_RESET_TOKEN_LENGTH = 128
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
CONTROL_CHARACTER_LIMIT = 32
DELETE_CHARACTER = 127


class ResetConfigurationError(Exception):
    pass


class InvalidResetLink(Exception):
    pass


def reset_destination():
    origin = settings.PASSWORD_RESET_PUBLIC_ORIGIN
    path = settings.PASSWORD_RESET_FRONTEND_PATH
    try:
        if (
            not isinstance(origin, str)
            or not origin
            or any(
                char.isspace()
                or ord(char) < CONTROL_CHARACTER_LIMIT
                or ord(char) == DELETE_CHARACTER
                for char in origin
            )
        ):
            raise ValueError()
        URLValidator(schemes=["http", "https"])(origin)
        parts = urlsplit(origin)
        if parts.port == 0 or not isinstance(path, str):
            raise ValueError()
        if (
            parts.username is not None
            or parts.password is not None
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
        ):
            raise ValueError()
        if parts.scheme != "https" and not (settings.DEBUG and parts.hostname in LOOPBACK_HOSTS):
            raise ValueError()
        if path and (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or any(
                char.isspace()
                or char in "\\?#"
                or ord(char) < CONTROL_CHARACTER_LIMIT
                or ord(char) == DELETE_CHARACTER
                for char in path
            )
        ):
            raise ValueError()
        return origin.rstrip("/"), path
    except (ValidationError, ValueError, TypeError):
        raise ResetConfigurationError() from None


def send_recovery_instructions(form):
    # Resolve configuration for every valid email, before matching any account.
    origin, frontend_path = reset_destination()
    for user in form.get_users(form.cleaned_data["email"]):
        uid = urlsafe_base64_encode(force_bytes(user._meta.pk.value_to_string(user)))
        token = default_token_generator.make_token(user)
        if frontend_path:
            link = origin + frontend_path + "#" + urlencode({"uidb64": uid, "token": token})
        else:
            link = origin + reverse(
                "password_reset_confirm", kwargs={"uidb64": uid, "token": token}
            )
        body = (
            f"A password reset was requested for your NHL Web App account ({user.get_username()}).\n\n"
            f"Open this link to choose a new password:\n{link}\n\n"
            "If you did not request this, you can ignore this email.\n"
        )
        try:
            sent = EmailMessage(
                PASSWORD_RESET_SUBJECT,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [getattr(user, user.get_email_field_name())],
            ).send()
            if sent != EXPECTED_MAIL_COUNT:
                logger.error("Password reset delivery did not report a sent message")
        except Exception as error:
            # SMTP exception text may contain addresses or other sensitive content.
            logger.error("Password reset delivery failed (%s)", type(error).__name__)


def user_from_uid(uidb64, *, lock=False):
    model = get_user_model()
    try:
        if not isinstance(uidb64, str) or not uidb64 or len(uidb64) > MAX_RESET_UID_LENGTH:
            raise ValueError()
        value = urlsafe_base64_decode(uidb64).decode()
        if not value.isascii() or not value.isdecimal():
            raise ValueError()
        uid = model._meta.pk.to_python(value)
        _, maximum = connection.ops.integer_field_range(model._meta.pk.get_internal_type())
        if uid <= 0 or (maximum is not None and uid > maximum):
            raise ValueError()
        queryset = model._default_manager.select_for_update() if lock else model._default_manager
        return queryset.get(pk=uid)
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        OverflowError,
        ValidationError,
        model.DoesNotExist,
    ):
        raise InvalidResetLink() from None


def check_reset_user(user, token, token_generator):
    if (
        not user.is_active
        or not user.has_usable_password()
        or not isinstance(token, str)
        or not token
        or len(token) > MAX_RESET_TOKEN_LENGTH
        or not token_generator.check_token(user, token)
    ):
        raise InvalidResetLink()


def validate_reset_link(uidb64, token, *, token_generator=default_token_generator):
    user = user_from_uid(uidb64)
    check_reset_user(user, token, token_generator)


def consume_reset_link(
    uidb64, token, data, *, form_class=SetPasswordForm, token_generator=default_token_generator
):
    with transaction.atomic():
        user = user_from_uid(uidb64, lock=True)
        check_reset_user(user, token, token_generator)
        form = form_class(user, data)
        if not form.is_valid():
            return form, None
        return form, form.save()
