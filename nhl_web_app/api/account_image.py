"""Dedicated multipart profile-image writes; ordinary API parsers stay JSON-only."""

from django.core.exceptions import ValidationError as FormValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import UnsupportedMediaType, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from players.api.saved_views import PrivateSavedListView, SAVED_LIST_ERRORS, validate_empty_mutation
from players.saved_actions import locked_user
from users.account_settings import profile_for
from users.profile_images import image_changes, validate_avatar
from .account import AccountSerializer, account_data
from .auth_views import CSRF_HEADER, validate_query
from .errors import AccountProfileUnavailable


class AccountImageInputSerializer(serializers.Serializer):
    image = serializers.FileField(
        help_text="One still PNG/JPEG/WebP image, at most 5 MiB, 20 million pixels and 8192 pixels per dimension. Names/MIME claims do not select the stored format or path."
    )

    def to_internal_value(self, data):
        errors = {key: ["Unsupported field."] for key in data if key != "image"}
        for key in data:
            if hasattr(data, "getlist") and len(data.getlist(key)) != 1:
                errors[key] = ["Supply this field once."]
        if errors:
            raise ValidationError(errors)
        return super().to_internal_value(data)

    def validate_image(self, value):
        try:
            return validate_avatar(value)
        except FormValidationError as error:
            raise ValidationError(error.messages) from None


class AccountImageView(PrivateSavedListView):
    # JSON remains useful only for the common empty DELETE object contract.
    # PUT enforces multipart explicitly; no global parser policy is relaxed.
    parser_classes = [MultiPartParser, JSONParser]

    @extend_schema(
        operation_id="me_account_image_put",
        tags=["account"],
        parameters=[CSRF_HEADER],
        request={"multipart/form-data": AccountImageInputSerializer},
        responses={status.HTTP_200_OK: AccountSerializer, **SAVED_LIST_ERRORS},
        description="Replace this session account's image using exactly one multipart image file. PNG/JPEG/WebP still images only; 5 MiB/20M pixels/8192 dimension limits, full decode and existing form validation. Generated unique storage name uses detected format. Requires CSRF and an existing profile. Returns the account snapshot; other settings are unchanged. New unreferenced files are cleaned after failed requests, old managed files only after commit and only if no profile references them. Storage cleanup failures are logged without turning a committed update into a false error.",
    )
    def put(self, request):
        validate_query(request)
        if request._request.content_type != "multipart/form-data":
            raise UnsupportedMediaType(request._request.content_type or "unspecified")
        payload = AccountImageInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with image_changes() as images, transaction.atomic():
            with locked_user(request.user) as owner:
                profile = profile_for(owner, lock=True)
                if profile is None:
                    raise AccountProfileUnavailable()
                images.stage(profile, payload.validated_data["image"])
                profile.save(update_fields=["image"])
                return Response(AccountSerializer(account_data(owner, profile)).data)

    @extend_schema(
        operation_id="me_account_image_delete",
        tags=["account"],
        parameters=[CSRF_HEADER],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None, **SAVED_LIST_ERRORS},
        description="Restore the configured default profile image, 204 including already default. Session/CSRF and an existing profile required; empty body/JSON object only, no queries. After commit deletes an old managed file only when unreferenced; defaults/shared files remain protected. No changes to account names, preferences, passwords or sessions.",
    )
    def delete(self, request):
        validate_empty_mutation(request)
        with image_changes() as images, transaction.atomic():
            with locked_user(request.user) as owner:
                profile = profile_for(owner, lock=True)
                if profile is None:
                    raise AccountProfileUnavailable()
                previous = profile.image.name
                images.reset(profile)
                if profile.image.name != previous:
                    profile.save(update_fields=["image"])
                return Response(status=status.HTTP_204_NO_CONTENT)
