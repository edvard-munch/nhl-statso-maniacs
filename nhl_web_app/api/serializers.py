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
