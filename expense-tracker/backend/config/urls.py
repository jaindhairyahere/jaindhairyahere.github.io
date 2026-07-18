"""Root URL configuration."""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView


def healthcheck(_request):
    """Lightweight liveness probe (no auth, no DB)."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz/", healthcheck, name="healthz"),
    path("admin/", admin.site.urls),
    # Google social login flow (server-driven redirect).
    path("accounts/", include("allauth.urls")),
    # Versioned API.
    path("api/v1/", include("config.api_urls")),
    # Same-origin SPA (Bootstrap + React via CDN).
    path("", TemplateView.as_view(template_name="index.html"), name="app"),
]
