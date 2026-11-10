"""Stable error envelopes shared by DRF and API-scoped Django failures."""

import logging

from django.http import JsonResponse
from django.utils.cache import add_never_cache_headers
from django.views.csrf import csrf_failure as django_csrf_failure
from rest_framework import exceptions, status

from . import is_api_request

logger = logging.getLogger(__name__)
ERROR_MARKER = "_api_error_normalized"
STATUS_ERRORS = {
    status.HTTP_400_BAD_REQUEST: ("invalid_request", "Invalid request."),
    status.HTTP_401_UNAUTHORIZED: ("authentication_required", "Sign in required."),
    status.HTTP_403_FORBIDDEN: ("permission_denied", "Permission denied."),
    status.HTTP_404_NOT_FOUND: ("not_found", "Resource not found."),
    status.HTTP_405_METHOD_NOT_ALLOWED: ("method_not_allowed", "Method not allowed."),
    status.HTTP_406_NOT_ACCEPTABLE: ("not_acceptable", "Only JSON responses are available."),
    status.HTTP_409_CONFLICT: ("conflict", "Request conflicts with current state."),
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: (
        "unsupported_media_type",
        "Unsupported request media type.",
    ),
    status.HTTP_429_TOO_MANY_REQUESTS: ("throttled", "Too many requests. Retry later."),
}
SERVER_ERROR = ("server_error", "An internal error occurred.")


class CsrfFailed(exceptions.PermissionDenied):
    default_detail = "CSRF validation failed."
    default_code = "csrf_failed"


class InvalidCredentials(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Unable to sign in with those credentials."
    default_code = "invalid_credentials"


def payload(code, message, fields=None):
    detail = {"code": code, "message": message}
    if fields is not None:
        detail["fields"] = fields
    return {"error": detail}


def mark_error(response):
    setattr(response, ERROR_MARKER, True)
    add_never_cache_headers(response)
    return response


def status_error(status_code):
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return SERVER_ERROR
    return STATUS_ERRORS.get(status_code, ("request_failed", "Request failed."))


def json_error(status_code, code=None, message=None):
    default_code, default_message = status_error(status_code)
    return mark_error(
        JsonResponse(payload(code or default_code, message or default_message), status=status_code)
    )


def exception_handler(exc, context):
    from rest_framework.views import exception_handler as drf_exception_handler

    response = drf_exception_handler(exc, context)
    if response is None:
        # Django's API boundary handles and logs unexpected exceptions.
        return None
    if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error("API server error", exc_info=(type(exc), exc, exc.__traceback__))
    code, message = status_error(response.status_code)
    fields = None
    if isinstance(exc, exceptions.ValidationError):
        code, message = "invalid_parameters", "Invalid request."
        fields = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
    elif isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        code, message = "authentication_required", "Sign in required."
    elif isinstance(exc, CsrfFailed):
        code, message = "csrf_failed", "CSRF validation failed."
    elif isinstance(exc, InvalidCredentials):
        code, message = "invalid_credentials", "Unable to sign in with those credentials."
    elif isinstance(exc, exceptions.ParseError):
        code, message = "parse_error", "Malformed request body."
    response.data = payload(code, message, fields)
    return mark_error(response)


def csrf_failure(request, reason="", template_name="403_csrf.html"):
    if is_api_request(request):
        return json_error(status.HTTP_403_FORBIDDEN, "csrf_failed", "CSRF validation failed.")
    return django_csrf_failure(request, reason=reason, template_name=template_name)
