from django.urls import path

from apps.core.views import CurrenciesView, FeatureFlagsView, FxConvertView

urlpatterns = [
    path("features/", FeatureFlagsView.as_view(), name="features"),
    path("currencies/", CurrenciesView.as_view(), name="currencies"),
    path("fx/convert/", FxConvertView.as_view(), name="fx-convert"),
]
