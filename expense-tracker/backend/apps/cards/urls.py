from rest_framework.routers import DefaultRouter

from apps.cards.views import (
    CashbackCheckView,
    CashbackProgramViewSet,
    CreditCardViewSet,
    WalletViewSet,
)

router = DefaultRouter()
router.register("cards", CreditCardViewSet, basename="card")
router.register("cashback-programs", CashbackProgramViewSet, basename="cashback-program")
router.register("wallets", WalletViewSet, basename="wallet")
router.register("cashback", CashbackCheckView, basename="cashback")

urlpatterns = router.urls
