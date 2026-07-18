from rest_framework.routers import DefaultRouter

from apps.expenses.views import CategoryViewSet, CommentViewSet, ExpenseViewSet

router = DefaultRouter()
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("comments", CommentViewSet, basename="comment")
router.register("categories", CategoryViewSet, basename="category")

urlpatterns = router.urls
