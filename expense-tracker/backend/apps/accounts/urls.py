from django.urls import path

from apps.accounts.views import CsrfView, LogoutView, MeView

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="csrf"),
    path("me/", MeView.as_view(), name="me"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
