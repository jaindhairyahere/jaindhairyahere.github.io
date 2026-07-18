from django.urls import path

from apps.analytics.views import (
    CardAnalyticsView,
    GroupAnalyticsView,
    PersonalAnalyticsView,
)

urlpatterns = [
    path("analytics/group/", GroupAnalyticsView.as_view(), name="analytics-group"),
    path("analytics/me/", PersonalAnalyticsView.as_view(), name="analytics-me"),
    path("analytics/cards/", CardAnalyticsView.as_view(), name="analytics-cards"),
]
