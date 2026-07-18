"""Shared enums and constants."""
from django.db import models


class Currency(models.TextChoices):
    """Supported currencies. Kept intentionally small (3) per requirements."""

    INR = "INR", "Indian Rupee"
    USD = "USD", "US Dollar"
    EUR = "EUR", "Euro"


# Number of decimal places we persist for monetary amounts.
MONEY_DECIMAL_PLACES = 2
MONEY_MAX_DIGITS = 18

# FX rates stored with high precision to avoid rounding drift on conversion.
FX_DECIMAL_PLACES = 10
FX_MAX_DIGITS = 20
