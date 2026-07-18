from django.contrib import admin

from apps.cards.models import CashbackProgram, CreditCard, Wallet


class CashbackProgramInline(admin.TabularInline):
    model = CashbackProgram
    extra = 0


@admin.register(CreditCard)
class CreditCardAdmin(admin.ModelAdmin):
    # Never surface encrypted fields in the admin.
    list_display = ("display_name", "issuer", "network", "group", "owner", "is_active", "has_last4")
    list_filter = ("network", "is_active")
    search_fields = ("display_name", "issuer")
    raw_id_fields = ("group", "owner")
    exclude = ("last4_enc", "expiry_enc")
    inlines = [CashbackProgramInline]


@admin.register(CashbackProgram)
class CashbackProgramAdmin(admin.ModelAdmin):
    list_display = ("card", "merchant", "percent", "currency", "payout", "is_active")
    list_filter = ("is_active", "currency", "payout")
    raw_id_fields = ("card", "wallet")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "group", "coin_rate", "currency", "is_active")
    list_filter = ("is_active", "currency")
    raw_id_fields = ("group", "owner")
