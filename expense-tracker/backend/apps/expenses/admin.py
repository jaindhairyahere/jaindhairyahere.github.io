from django.contrib import admin

from apps.expenses.models import (
    CashbackAccrual,
    Comment,
    Expense,
    ExpensePayer,
    ExpenseSplit,
)


class ExpensePayerInline(admin.TabularInline):
    model = ExpensePayer
    extra = 0
    raw_id_fields = ("member",)


class ExpenseSplitInline(admin.TabularInline):
    model = ExpenseSplit
    extra = 0
    raw_id_fields = ("member",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "description", "group", "total_amount", "currency", "base_amount",
        "cashback_amount", "date", "payment_mode",
    )
    list_filter = ("currency", "payment_mode", "date")
    search_fields = ("description", "merchant")
    raw_id_fields = ("group", "card", "cashback_program", "created_by")
    inlines = [ExpensePayerInline, ExpenseSplitInline]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("expense", "author", "created_at")
    raw_id_fields = ("expense", "author")


@admin.register(CashbackAccrual)
class CashbackAccrualAdmin(admin.ModelAdmin):
    list_display = ("program", "card", "amount", "currency", "accrued_on")
    list_filter = ("currency", "accrued_on")
    raw_id_fields = ("expense", "program", "card")
