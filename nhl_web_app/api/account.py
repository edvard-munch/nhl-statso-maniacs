"""Current-account JSON settings; image uploads use a separate multipart resource."""

from collections.abc import Mapping

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from players.api.saved_views import PrivateSavedListView, SAVED_LIST_ERRORS
from players.saved_actions import locked_user
from users.account_settings import edit_account, profile_for
from users.choices import MEASUREMENTS_FORMAT_CHOICES
from .auth_views import CSRF_HEADER, json_body, validate_query
from .errors import AccountProfileUnavailable
from .registration import RegistrationUsernameField, RegistrationEmailField
from .serializers import form_error_fields


class AccountPatchSerializer(serializers.Serializer):
    username = RegistrationUsernameField(required=False)
    email = RegistrationEmailField(required=False)
    measurements_format = serializers.ChoiceField(
        choices=MEASUREMENTS_FORMAT_CHOICES, required=False
    )

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = {key: ["Unsupported field."] for key in data if key not in self.fields}
            if unknown:
                raise ValidationError(unknown)
        return super().to_internal_value(data)


class AccountProfileSerializer(serializers.Serializer):
    measurements_format = serializers.ChoiceField(
        choices=MEASUREMENTS_FORMAT_CHOICES, allow_null=True
    )
    image_url = serializers.CharField(allow_null=True)


class AccountSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    profile = AccountProfileSerializer(allow_null=True)


def account_data(user, profile):
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "profile": {
            "measurements_format": profile.measurements_format
            if profile.measurements_format in dict(MEASUREMENTS_FORMAT_CHOICES)
            else None,
            "image_url": profile.image.url if profile.image else None,
        }
        if profile is not None
        else None,
    }


class AccountView(PrivateSavedListView):
    @extend_schema(
        operation_id="me_account_retrieve",
        tags=["account"],
        responses={status.HTTP_200_OK: AccountSerializer, **SAVED_LIST_ERRORS},
        description="Current session account's username/email and profile measurement preference/read-only image URL. No query parameters or account selectors. Missing profile is null; GET never creates/repairs it. Private/no-store, owner-locked reads; public statistics and session bootstrap remain unchanged.",
    )
    def get(self, request):
        validate_query(request)
        with locked_user(request.user) as owner:
            return Response(AccountSerializer(account_data(owner, profile_for(owner))).data)

    @extend_schema(
        operation_id="me_account_patch",
        tags=["account"],
        parameters=[CSRF_HEADER],
        request=AccountPatchSerializer,
        responses={status.HTTP_200_OK: AccountSerializer, **SAVED_LIST_ERRORS},
        description="Partial explicit settings update: username, email, measurements_format only. Requires JSON object, session and CSRF; rejects unknown fields/queries, files and privilege/password inputs. Uses shared HTML forms, normalized case-insensitive username policy and the registration name lock. Omitted fields are preserved; empty object is a no-op. User/profile writes and response serialization are atomic under owner/profile locks. Missing profile returns 409 account_profile_unavailable. No password/session rotation or image writes.",
    )
    def patch(self, request):
        validate_query(request)
        payload = AccountPatchSerializer(data=json_body(request))
        payload.is_valid(raise_exception=True)
        with edit_account(request.user, payload.validated_data) as edit:
            if edit.profile is None:
                raise AccountProfileUnavailable()
            if not edit.valid:
                errors = {}
                for form in (edit.user_form, edit.measurements_form):
                    if form is not None:
                        errors.update(form_error_fields(form))
                raise ValidationError(errors)
            return Response(AccountSerializer(account_data(edit.user, edit.profile)).data)
