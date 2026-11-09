"""Describe the API's session-cookie authentication to OpenAPI generators."""

from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SessionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "nhl_web_app.api.authentication.SessionAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME}
