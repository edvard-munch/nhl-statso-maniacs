"""Explicit reusable schema components; model serialization follows per resource."""

from rest_framework import serializers


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    fields = serializers.DictField(required=False)


class ErrorResponseSerializer(serializers.Serializer):
    error = ErrorDetailSerializer()


class ApiVersionSerializer(serializers.Serializer):
    version = serializers.CharField()


def form_error_fields(form):
    """Translate Django form errors without exposing raw form input."""
    from django.core.exceptions import NON_FIELD_ERRORS

    return {
        "non_field_errors" if field == NON_FIELD_ERRORS else field: [
            message for error in errors for message in error.messages
        ]
        for field, errors in form.errors.as_data().items()
    }
