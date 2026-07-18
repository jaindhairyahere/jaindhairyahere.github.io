from rest_framework.routers import DefaultRouter

from apps.groups.views import GroupViewSet, MemberViewSet

router = DefaultRouter()
router.register("groups", GroupViewSet, basename="group")
router.register("members", MemberViewSet, basename="member")

urlpatterns = router.urls
