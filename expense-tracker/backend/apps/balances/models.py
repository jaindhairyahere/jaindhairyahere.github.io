"""Settlement: a recorded payment from one member to another."""
from django.conf import settings
from django.db import models

from apps.core.base_models import TimeStampedModel
from apps.core.enums import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS, Currency


class Settlement(TimeStampedModel):
    group = models.ForeignKey("groups.Group", on_delete=models.CASCADE, related_name="settlements")
    from_member = models.ForeignKey(
        "members.Member", on_delete=models.PROTECT, related_name="settlements_paid"
    )
    to_member = models.ForeignKey(
        "members.Member", on_delete=models.PROTECT, related_name="settlements_received"
    )
    amount = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    date = models.DateField()
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="settlements_created"
    )

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.from_member} -> {self.to_member}: {self.amount} {self.currency}"
