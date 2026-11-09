"""Preserve session authentication while identifying CSRF errors by code."""

from rest_framework.authentication import SessionAuthentication as DRFSessionAuthentication
from rest_framework.exceptions import PermissionDenied

from .errors import CsrfFailed


class SessionAuthentication(DRFSessionAuthentication):
    def enforce_csrf(self, request):
        try:
            return super().enforce_csrf(request)
        except PermissionDenied as error:
            raise CsrfFailed() from error
