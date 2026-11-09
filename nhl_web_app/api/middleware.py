"""Normalize Django failures only inside the new API boundary."""

import logging
from uuid import uuid4

from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404
from rest_framework import status

from nhl_web_app.logging_config import bind_context

from . import is_api_request
from .errors import ERROR_MARKER, json_error

logger = logging.getLogger(__name__)
REQUEST_ID_HEADER = "X-Request-ID"
# Representation headers cease to describe the body when an error is replaced.
REPLACED_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "content-encoding",
        "etag",
        "content-md5",
        "content-disposition",
        "location",
    }
)


class ApiBoundaryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not is_api_request(request):
            return self.get_response(request)
        request.api_request_id = str(uuid4())
        with bind_context(request_id=request.api_request_id):
            response = self.get_response(request)
            if response.status_code >= status.HTTP_400_BAD_REQUEST and not getattr(
                response, ERROR_MARKER, False
            ):
                original = response
                response = json_error(original.status_code)
                for name, value in original.items():
                    if name.lower() not in REPLACED_HEADERS and name.lower() not in {
                        "cache-control",
                        "expires",
                    }:
                        response[name] = value
                response.cookies = original.cookies
            response[REQUEST_ID_HEADER] = request.api_request_id
            return response

    def process_exception(self, request, exception):
        if not is_api_request(request):
            return None
        if isinstance(exception, Http404):
            return json_error(status.HTTP_404_NOT_FOUND)
        if isinstance(exception, PermissionDenied):
            return json_error(status.HTTP_403_FORBIDDEN)
        if isinstance(exception, (BadRequest, SuspiciousOperation)):
            return json_error(status.HTTP_400_BAD_REQUEST)
        logger.error(
            "Unhandled API exception",
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        return json_error(status.HTTP_500_INTERNAL_SERVER_ERROR)
