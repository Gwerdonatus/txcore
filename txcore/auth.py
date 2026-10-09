from drf_spectacular.utils import extend_schema
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework import serializers
from rest_framework.throttling import AnonRateThrottle


class TokenResponse(serializers.Serializer):
    token = serializers.CharField()


class WorkspaceTokenView(ObtainAuthToken):
    throttle_classes = [AnonRateThrottle]

    @extend_schema(tags=["Authentication"], responses={200: TokenResponse})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
