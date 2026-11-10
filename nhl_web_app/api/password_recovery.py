"""JSON password recovery using Django's eligibility, token and password rules."""

from collections.abc import Mapping
import logging

from django.contrib.auth.forms import PasswordResetForm
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from users.password_recovery import (
    InvalidResetLink,
    ResetConfigurationError,
    MAX_RESET_UID_LENGTH,
    MAX_RESET_TOKEN_LENGTH,
    consume_reset_link,
    send_recovery_instructions,
    validate_reset_link,
)
from .auth_views import AUTH_ERRORS, CSRF_HEADER, SessionLifecycleView, json_body, validate_query
from .registration import RegistrationEmailField, RegistrationPasswordField, RegistrationTextField
from .serializers import ErrorResponseSerializer, form_error_fields
from .errors import InvalidResetToken, ResetUnavailable

logger = logging.getLogger(__name__)


class StrictRecoverySerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = {key: ["Unsupported field."] for key in data if key not in self.fields}
            if unknown:
                raise serializers.ValidationError(unknown)
        return super().to_internal_value(data)


class PasswordRecoveryRequestSerializer(StrictRecoverySerializer):
    email = RegistrationEmailField()


class ResetLinkSerializer(StrictRecoverySerializer):
    uidb64 = RegistrationTextField()
    token = RegistrationTextField(write_only=True)

    def validate(self, attrs):
        if (
            not attrs["uidb64"]
            or len(attrs["uidb64"]) > MAX_RESET_UID_LENGTH
            or not attrs["token"]
            or len(attrs["token"]) > MAX_RESET_TOKEN_LENGTH
        ):
            raise InvalidResetToken()
        return attrs


class NewPasswordSerializer(ResetLinkSerializer):
    new_password1 = RegistrationPasswordField(write_only=True)
    new_password2 = RegistrationPasswordField(write_only=True)


class RecoveryAcceptedSerializer(serializers.Serializer):
    accepted = serializers.BooleanField(
        help_text="Generic acknowledgement, not proof of an account match or successful delivery."
    )


class ResetValidSerializer(serializers.Serializer):
    valid = serializers.BooleanField()


class PasswordChangedSerializer(serializers.Serializer):
    password_reset = serializers.BooleanField()
    login_required = serializers.BooleanField()


def reset_errors():
    return {**AUTH_ERRORS, status.HTTP_503_SERVICE_UNAVAILABLE: ErrorResponseSerializer}


class PasswordRecoveryRequestView(SessionLifecycleView):
    @extend_schema(
        operation_id="auth_password_reset_create",
        tags=["auth"],
        parameters=[CSRF_HEADER],
        request=PasswordRecoveryRequestSerializer,
        responses={status.HTTP_200_OK: RecoveryAcceptedSerializer, **reset_errors()},
        description="CSRF-protected recovery request with required email. Same acknowledgement for eligible, unknown, inactive or unusable-password accounts and mail delivery failure. Links use only configured public origin, never request Host/forwarded headers. Current Django email-match eligibility is preserved. Delivery is synchronous; no constant-time guarantee. Missing/unsafe destination configuration returns 503 for every valid email.",
    )
    def post(self, request):
        validate_query(request)
        data = PasswordRecoveryRequestSerializer(data=json_body(request))
        data.is_valid(raise_exception=True)
        form = PasswordResetForm(data.validated_data)
        if not form.is_valid():
            raise ValidationError(form_error_fields(form))
        try:
            send_recovery_instructions(form)
        except ResetConfigurationError:
            logger.error("Password reset destination is not configured safely")
            raise ResetUnavailable() from None
        return Response(RecoveryAcceptedSerializer({"accepted": True}).data)


class ResetLinkView(SessionLifecycleView):
    @extend_schema(
        operation_id="auth_password_reset_validate_create",
        tags=["auth"],
        parameters=[CSRF_HEADER],
        request=ResetLinkSerializer,
        responses={status.HTTP_200_OK: ResetValidSerializer, **AUTH_ERRORS},
        description="CSRF-protected reset link check with uidb64/token in JSON, not URL/query. Valid links return valid=true without consuming the token or disclosing account data. Invalid, unknown-user, inactive, expired or used links share invalid_reset_token 400. Confirmation rechecks under a row lock.",
    )
    def post(self, request):
        validate_query(request)
        data = ResetLinkSerializer(data=json_body(request))
        data.is_valid(raise_exception=True)
        try:
            validate_reset_link(**data.validated_data)
        except InvalidResetLink:
            raise InvalidResetToken() from None
        return Response(ResetValidSerializer({"valid": True}).data)


class PasswordRecoveryConfirmView(SessionLifecycleView):
    @extend_schema(
        operation_id="auth_password_reset_confirm_create",
        tags=["auth"],
        parameters=[CSRF_HEADER],
        request=NewPasswordSerializer,
        responses={status.HTTP_200_OK: PasswordChangedSerializer, **AUTH_ERRORS},
        description="CSRF-protected password reset using uidb64/token and new_password1/new_password2 JSON. Token revalidation and SetPasswordForm save are atomic under a user-row lock, shared with HTML confirmation. Success requires a separate login; existing target sessions become invalid by Django's password hash. No user details/token are returned. Invalid links share invalid_reset_token 400; password errors are field-specific.",
    )
    def post(self, request):
        validate_query(request)
        data = NewPasswordSerializer(data=json_body(request))
        data.is_valid(raise_exception=True)
        fields = data.validated_data
        try:
            form, user = consume_reset_link(
                fields["uidb64"],
                fields["token"],
                {key: fields[key] for key in ("new_password1", "new_password2")},
            )
        except InvalidResetLink:
            raise InvalidResetToken() from None
        if user is None:
            raise ValidationError(form_error_fields(form))
        return Response(
            PasswordChangedSerializer({"password_reset": True, "login_required": True}).data
        )
