"""Version/schema endpoints; no statistics or auth lifecycle migration yet."""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from . import VERSION
from .serializers import ApiVersionSerializer, ErrorResponseSerializer


@method_decorator(never_cache, name="dispatch")
class ApiRootView(APIView):
    @extend_schema(
        operation_id="api_v1_root_retrieve",
        tags=["api"],
        responses={
            status.HTTP_200_OK: ApiVersionSerializer,
            status.HTTP_403_FORBIDDEN: ErrorResponseSerializer,
            status.HTTP_405_METHOD_NOT_ALLOWED: ErrorResponseSerializer,
            status.HTTP_406_NOT_ACCEPTABLE: ErrorResponseSerializer,
            status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorResponseSerializer,
        },
    )
    def get(self, request):
        return Response(ApiVersionSerializer({"version": VERSION}).data)


class SchemaView(SpectacularAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    renderer_classes = [JSONRenderer]


class NotFoundView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    schema = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        raise NotFound()
