"""Credit card + cashback program models.

Security: no full card number is ever stored. Optional ``last4``/``expiry``
are encrypted at rest and never exposed by the API (only booleans/status).
Cards are group-scoped and owned by a group ``Member``.
"""
from django.db import models

from apps.core.base_models import TimeStampedModel
from apps.core.encryption import EncryptedCharField
from apps.core.enums import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS, Currency


def _money(**kwargs):
    return models.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, **kwargs
    )


class CardNetwork(models.TextChoices):
    VISA = "visa", "Visa"
    MASTERCARD = "mastercard", "Mastercard"
    RUPAY = "rupay", "RuPay"
    AMEX = "amex", "American Express"
    OTHER = "other", "Other"


class CreditCard(TimeStampedModel):
    group = models.ForeignKey("groups.Group", on_delete=models.CASCADE, related_name="cards")
    owner = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="cards")
    display_name = models.CharField(max_length=150)
    issuer = models.CharField(max_length=100, blank=True)
    network = models.CharField(max_length=16, choices=CardNetwork.choices, default=CardNetwork.OTHER)
    billing_cycle_day = models.PositiveSmallIntegerField(null=True, blank=True)

    # Sensitive, encrypted at rest, never returned by the API.
    last4_enc = EncryptedCharField(null=True, blank=True)
    expiry_enc = EncryptedCharField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_name"]
        indexes = [models.Index(fields=["group", "is_active"])]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.issuer})" if self.issuer else self.display_name

    @property
    def has_last4(self) -> bool:
        return bool(self.last4_enc)


class Wallet(TimeStampedModel):
    """A coin/points wallet owned by a member (e.g. Flipkart Coins).

    Coins have a fractional currency value (``coin_rate`` = value of 1 coin)
    and can expire. Coin cashback is a personal perk for the owner and does
    NOT reduce what group members owe.
    """

    group = models.ForeignKey("groups.Group", on_delete=models.CASCADE, related_name="wallets")
    owner = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="wallets")
    name = models.CharField(max_length=120)  # e.g. "Flipkart Coins"
    coin_rate = models.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=6, default=1
    )  # value in `currency` of 1 coin, e.g. 0.25
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.INR)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.owner.display_name})"


class PayoutType(models.TextChoices):
    CASH = "cash", "Cash (reduces what borrowers owe)"
    COINS = "coins", "Wallet coins (personal perk, does not reduce debt)"


class CashbackProgram(TimeStampedModel):
    """A cashback rule on a card for a merchant, with amount + count limits.

    ``merchant`` matches ``Expense.merchant`` case-insensitively; use ``ANY``
    to match every merchant. All monetary caps are in the group base currency.
    """

    ANY_MERCHANT = "ANY"

    card = models.ForeignKey(CreditCard, on_delete=models.CASCADE, related_name="programs")
    merchant = models.CharField(max_length=120, default=ANY_MERCHANT)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.INR)
    is_active = models.BooleanField(default=True)

    # Payout: cash reduces debt; coins are a personal perk paid into a wallet.
    payout = models.CharField(max_length=8, choices=PayoutType.choices, default=PayoutType.CASH)
    wallet = models.ForeignKey(
        Wallet, on_delete=models.SET_NULL, null=True, blank=True, related_name="programs"
    )
    coin_expiry_days = models.PositiveIntegerField(null=True, blank=True)

    # Amount caps (max cashback), in ``currency``. Null = no cap.
    max_per_txn = _money(null=True, blank=True)
    cap_per_day = _money(null=True, blank=True)
    cap_per_week = _money(null=True, blank=True)
    cap_per_month = _money(null=True, blank=True)
    cap_per_year = _money(null=True, blank=True)
    cap_total = _money(null=True, blank=True)

    # Count caps (number of cashback "vouches"). Null = no cap.
    max_vouches_total = models.PositiveIntegerField(null=True, blank=True)
    max_per_day = models.PositiveIntegerField(null=True, blank=True)
    max_per_week = models.PositiveIntegerField(null=True, blank=True)
    max_per_month = models.PositiveIntegerField(null=True, blank=True)
    max_per_year = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-percent"]
        indexes = [models.Index(fields=["card", "is_active"])]

    def __str__(self) -> str:
        return f"{self.card.display_name}: {self.percent}% @ {self.merchant}"
