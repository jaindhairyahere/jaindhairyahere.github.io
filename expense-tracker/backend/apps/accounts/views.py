"""Auth API: CSRF bootstrap, current-user, logout."""
from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Profile


def _google_configured() -> bool:
    provider = settings.SOCIALACCOUNT_PROVIDERS.get("google", {})
    return bool(provider.get("APP", {}).get("client_id"))


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["display_name", "avatar_url", "plan"]


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    profile = ProfileSerializer()


class CsrfView(APIView):
    """Return a CSRF token + public auth config (call before mutating requests)."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "csrftoken": get_token(request),
                "google_configured": _google_configured(),
                "debug": settings.DEBUG,
            }
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            MeSerializer(
                {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "profile": user.profile,
                }
            ).data
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        django_logout(request)
        return Response({"detail": "Logged out."})
