"""Core models: cached daily FX rates."""
from django.db import models

from apps.core.base_models import TimeStampedModel
from apps.core.enums import FX_DECIMAL_PLACES, FX_MAX_DIGITS, Currency


class DailyFxRate(TimeStampedModel):
    """A cached foreign-exchange rate for a (base -> quote) pair on a date.

    ``rate`` means: 1 unit of ``base`` = ``rate`` units of ``quote``.
    One row per (base, quote, date); refreshed at most once/day from the
    provider. Used to snapshot ``fx_rate`` onto each expense at record time.
    """

    base = models.CharField(max_length=3, choices=Currency.choices)
    quote = models.CharField(max_length=3, choices=Currency.choices)
    rate = models.DecimalField(max_digits=FX_MAX_DIGITS, decimal_places=FX_DECIMAL_PLACES)
    as_of = models.DateField(db_index=True)
    source = models.CharField(max_length=32, default="frankfurter")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["base", "quote", "as_of"], name="uniq_fx_pair_per_day"
            )
        ]
        indexes = [models.Index(fields=["base", "quote", "as_of"])]

    def __str__(self) -> str:
        return f"{self.base}->{self.quote} @ {self.rate} ({self.as_of})"
