"""Shared JSON API foundation; statistics resources are migrated separately."""

VERSION = "v1"
PREFIX = f"/api/{VERSION}/"


def is_api_request(request):
    return request.path_info == PREFIX.rstrip("/") or request.path_info.startswith(PREFIX)
