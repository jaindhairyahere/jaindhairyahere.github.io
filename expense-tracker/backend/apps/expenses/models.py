"""Expense models: expense, its payers/splits, comments and cashback ledger."""
from django.conf import settings
from django.db import models

from apps.core.base_models import TimeStampedModel
from apps.core.enums import (
    FX_DECIMAL_PLACES,
    FX_MAX_DIGITS,
    MONEY_DECIMAL_PLACES,
    MONEY_MAX_DIGITS,
    Currency,
)


def _money(**kwargs):
    return models.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, **kwargs
    )


class PaymentMode(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Credit/Debit Card"
    UPI = "upi", "UPI"
    BANK = "bank", "Bank Transfer"
    OTHER = "other", "Other"


class SplitType(models.TextChoices):
    EQUAL = "equal", "Equal"
    EXACT = "exact", "Exact"
    PERCENT = "percent", "Percent"


class Category(models.Model):
    """A global expense category (shared across all groups/users)."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    icon = models.CharField(max_length=8, blank=True)  # emoji
    sort_order = models.PositiveSmallIntegerField(default=100)
    # Maps to a Splitwise parent-category name for import (best-effort).
    splitwise_names = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Expense(TimeStampedModel):
    group = models.ForeignKey("groups.Group", on_delete=models.CASCADE, related_name="expenses")
    description = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )
    currency = models.CharField(max_length=3, choices=Currency.choices)
    total_amount = _money()

    # FX snapshot at record time: 1 unit of ``currency`` = ``fx_rate`` base units.
    fx_rate = models.DecimalField(max_digits=FX_MAX_DIGITS, decimal_places=FX_DECIMAL_PLACES, default=1)
    base_amount = _money()  # total in the group's base currency

    date = models.DateField()
    merchant = models.CharField(max_length=120, blank=True)
    payment_mode = models.CharField(
        max_length=16, choices=PaymentMode.choices, default=PaymentMode.CASH
    )
    card = models.ForeignKey(
        "cards.CreditCard", on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )
    cashback_program = models.ForeignKey(
        "cards.CashbackProgram", on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )
    # Cashback granted, in the group base currency. Reduces what borrowers owe.
    cashback_amount = _money(default=0)

    # When True this expense is kept as a direct debt, excluded from group
    # min-cash-flow simplification.
    simplify_override = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="expenses_created"
    )

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["group", "date"])]

    def __str__(self) -> str:
        return f"{self.description} ({self.total_amount} {self.currency})"


class ExpensePayer(models.Model):
    """Who fronted money for the expense (can be several)."""

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="payers")
    member = models.ForeignKey("members.Member", on_delete=models.PROTECT, related_name="paid_for")
    amount_paid = _money()  # in expense currency

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "member"], name="uniq_expense_payer")
        ]


class ExpenseSplit(models.Model):
    """Who owes a share of the expense (can be several)."""

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="splits")
    member = models.ForeignKey("members.Member", on_delete=models.PROTECT, related_name="owes_for")
    share_amount = _money()  # in expense currency
    split_type = models.CharField(max_length=16, choices=SplitType.choices, default=SplitType.EQUAL)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "member"], name="uniq_expense_split")
        ]


class Comment(TimeStampedModel):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="comments"
    )
    body = models.TextField()

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Comment<{self.expense_id}>"


class CashbackAccrual(TimeStampedModel):
    """Ledger of granted cashback, used to enforce program limit windows."""

    expense = models.OneToOneField(
        Expense, on_delete=models.CASCADE, related_name="accrual", null=True, blank=True
    )
    program = models.ForeignKey(
        "cards.CashbackProgram", on_delete=models.CASCADE, related_name="accruals"
    )
    card = models.ForeignKey("cards.CreditCard", on_delete=models.CASCADE, related_name="accruals")
    amount = _money()  # granted cashback, program currency (== group base)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    accrued_on = models.DateField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["program", "accrued_on"])]

    def __str__(self) -> str:
        return f"Accrual<{self.amount} {self.currency}>"


class CoinAccrual(TimeStampedModel):
    """Ledger of coin/points cashback awarded to a wallet (personal perk).

    Does not affect group balances. ``coins`` valued at ``rate_at_award``;
    counts as a benefit only while unexpired.
    """

    expense = models.OneToOneField(
        Expense, on_delete=models.CASCADE, related_name="coin_accrual", null=True, blank=True
    )
    wallet = models.ForeignKey("cards.Wallet", on_delete=models.CASCADE, related_name="accruals")
    program = models.ForeignKey(
        "cards.CashbackProgram", on_delete=models.CASCADE, related_name="coin_accruals"
    )
    coins = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=4)
    rate_at_award = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=6)
    cash_value = _money()  # coins * rate_at_award, in wallet currency
    currency = models.CharField(max_length=3, choices=Currency.choices)
    awarded_on = models.DateField(db_index=True)
    expires_on = models.DateField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["wallet", "expires_on"])]

    def __str__(self) -> str:
        return f"CoinAccrual<{self.coins} coins>"
