from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.balances.views import BalanceView, SettlementViewSet

router = DefaultRouter()
router.register("settlements", SettlementViewSet, basename="settlement")

urlpatterns = [
    path("balances/", BalanceView.as_view(), name="balances"),
    *router.urls,
]
