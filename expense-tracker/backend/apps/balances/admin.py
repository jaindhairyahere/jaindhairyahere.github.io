from django.contrib import admin

from apps.balances.models import Settlement


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ("group", "from_member", "to_member", "amount", "currency", "date")
    list_filter = ("currency", "date")
    raw_id_fields = ("group", "from_member", "to_member", "created_by")
