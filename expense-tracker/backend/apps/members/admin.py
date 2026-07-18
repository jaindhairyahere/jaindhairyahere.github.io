from django.contrib import admin

from apps.members.models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("display_name", "group", "user", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("display_name",)
    raw_id_fields = ("group", "user")
