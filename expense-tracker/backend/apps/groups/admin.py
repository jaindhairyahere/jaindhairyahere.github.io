from django.contrib import admin

from apps.groups.models import Group


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "base_currency", "simplify_enabled", "created_by")
    list_filter = ("kind", "base_currency", "simplify_enabled")
    search_fields = ("name",)
