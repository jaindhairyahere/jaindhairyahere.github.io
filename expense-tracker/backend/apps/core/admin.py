from django.contrib import admin

from apps.core.models import DailyFxRate


@admin.register(DailyFxRate)
class DailyFxRateAdmin(admin.ModelAdmin):
    list_display = ("base", "quote", "rate", "as_of", "source")
    list_filter = ("base", "quote", "source", "as_of")
    search_fields = ("base", "quote")
