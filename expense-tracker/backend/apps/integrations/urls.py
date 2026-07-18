from django.urls import path

from apps.integrations.views import SplitwiseGroupsView, SplitwiseImportView

urlpatterns = [
    path("import/splitwise/groups/", SplitwiseGroupsView.as_view(), name="splitwise-groups"),
    path("import/splitwise/", SplitwiseImportView.as_view(), name="splitwise-import"),
]
