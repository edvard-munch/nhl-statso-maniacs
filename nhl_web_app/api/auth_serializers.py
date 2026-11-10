"""Minimal session identity and strict JSON credentials; no account editing."""

from collections.abc import Mapping

from django.contrib.auth import get_user_model
from rest_framework import serializers


class LoginTextField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class LoginUsernameField(LoginTextField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        # Match Django's login form normalization, avoiding work on overlong input.
        if self.max_length is None or len(value) <= self.max_length:
            value = get_user_model().normalize_username(value)
        return value


class LoginCredentialsSerializer(serializers.Serializer):
    username = LoginUsernameField(
        max_length=get_user_model()._meta.get_field(get_user_model().USERNAME_FIELD).max_length
    )
    password = LoginTextField(
        trim_whitespace=False, write_only=True, style={"input_type": "password"}
    )

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = {key: ["Unsupported field."] for key in data if key not in self.fields}
            if unknown:
                raise serializers.ValidationError(unknown)
        return super().to_internal_value(data)


class SessionUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()


class SessionResponseSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    user = SessionUserSerializer(allow_null=True)


class CsrfResponseSerializer(serializers.Serializer):
    csrf_token = serializers.CharField(
        help_text="Masked CSRF token for the X-CSRFToken header; works with HTTP-only and session-backed CSRF."
    )


class AuthResponseSerializer(SessionResponseSerializer):
    csrf_token = serializers.CharField(
        help_text="Fresh masked CSRF token after login/logout rotation. Replace the previous client token."
    )
