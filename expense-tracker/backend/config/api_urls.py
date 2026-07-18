"""Aggregated API v1 routes."""
from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.members.urls")),
    path("", include("apps.groups.urls")),
    path("", include("apps.expenses.urls")),
    path("", include("apps.cards.urls")),
    path("", include("apps.balances.urls")),
    path("", include("apps.analytics.urls")),
    path("", include("apps.integrations.urls")),
]
