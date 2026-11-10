"""CSRF-protected JSON registration, sharing HTML validation and persistence."""

from collections.abc import Mapping

from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from users.forms import UserRegisterForm
from users.registration import create_registered_user
from .auth_serializers import SessionUserSerializer
from .auth_views import AUTH_ERRORS, CSRF_HEADER, SessionLifecycleView, json_body, validate_query
from .serializers import form_error_fields


@extend_schema_field(OpenApiTypes.STR)
class RegistrationTextField(serializers.Field):
    """Check the JSON type; the shared form owns blank/length/content validation."""

    default_error_messages = {"invalid": "Not a valid string."}

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return data

    def to_representation(self, value):
        return value


@extend_schema_field(OpenApiTypes.EMAIL)
class RegistrationEmailField(RegistrationTextField):
    pass


@extend_schema_field(
    {
        "type": "string",
        "maxLength": UserRegisterForm._meta.model._meta.get_field("username").max_length,
    }
)
class RegistrationUsernameField(RegistrationTextField):
    pass


@extend_schema_field(OpenApiTypes.PASSWORD)
class RegistrationPasswordField(RegistrationTextField):
    pass


class RegistrationCredentialsSerializer(serializers.Serializer):
    username = RegistrationUsernameField()
    email = RegistrationEmailField()
    password1 = RegistrationPasswordField(write_only=True)
    password2 = RegistrationPasswordField(write_only=True)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = {key: ["Unsupported field."] for key in data if key not in self.fields}
            if unknown:
                raise serializers.ValidationError(unknown)
        return super().to_internal_value(data)


class RegistrationResponseSerializer(serializers.Serializer):
    user = SessionUserSerializer()
    login_required = serializers.BooleanField(
        help_text="The new account is not automatically signed in. Any existing caller session is preserved."
    )


class RegistrationView(SessionLifecycleView):
    @extend_schema(
        operation_id="auth_register_create",
        tags=["auth"],
        parameters=[CSRF_HEADER],
        request=RegistrationCredentialsSerializer,
        responses={status.HTTP_201_CREATED: RegistrationResponseSerializer, **AUTH_ERRORS},
        description="CSRF-protected JSON registration using the existing UserRegisterForm, password validators and profile signals. Requires username, email, password1 and password2. User/profile writes are atomic; both web flows serialize case-insensitive username collisions. Success requires a separate login and preserves the caller's session. Email remains required but non-unique, matching existing policy. No redirects or query parameters.",
    )
    def post(self, request):
        validate_query(request)
        credentials = RegistrationCredentialsSerializer(data=json_body(request))
        credentials.is_valid(raise_exception=True)
        form = UserRegisterForm(credentials.validated_data)
        user = create_registered_user(form)
        if user is None:
            raise ValidationError(form_error_fields(form))
        return Response(
            RegistrationResponseSerializer({"user": user, "login_required": True}).data,
            status=status.HTTP_201_CREATED,
        )
