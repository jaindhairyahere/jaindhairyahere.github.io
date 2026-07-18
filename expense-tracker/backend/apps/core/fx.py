"""FX conversion engine.

Fetches near-live daily rates from Frankfurter (ECB, no API key) with an
open.er-api.com fallback, caches them in ``DailyFxRate``, and converts
amounts between supported currencies. All conversions use ``Decimal``.
"""
from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.utils import timezone

from apps.core.enums import MONEY_DECIMAL_PLACES
from apps.core.models import DailyFxRate

_QUANT = Decimal(10) ** -MONEY_DECIMAL_PLACES


class FxError(Exception):
    """Raised when a rate cannot be resolved."""


def _quantize_money(amount: Decimal) -> Decimal:
    return amount.quantize(_QUANT, rounding=ROUND_HALF_UP)


def get_rate(base: str, quote: str, on: dt.date | None = None) -> Decimal:
    """Return the rate for ``1 base = ? quote`` on a date (default: today).

    Resolution order: identity -> cached row -> live fetch -> inverse of
    cached/live. Rates are cached per day.
    """
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return Decimal(1)
    on = on or timezone.localdate()

    cached = DailyFxRate.objects.filter(base=base, quote=quote, as_of=on).first()
    if cached:
        return cached.rate

    if settings.FX_LIVE_FETCH:
        rate = _fetch_and_cache(base, quote, on)
        if rate is not None:
            return rate

    # Fall back to the inverse of a known rate if available.
    inverse = DailyFxRate.objects.filter(base=quote, quote=base, as_of=on).first()
    if inverse and inverse.rate:
        return Decimal(1) / inverse.rate

    raise FxError(f"No FX rate available for {base}->{quote} on {on}")


def convert(amount: Decimal, base: str, quote: str, on: dt.date | None = None) -> Decimal:
    """Convert ``amount`` from ``base`` to ``quote`` and round to money scale."""
    return _quantize_money(Decimal(amount) * get_rate(base, quote, on))


def _fetch_and_cache(base: str, quote: str, on: dt.date) -> Decimal | None:
    rate = _fetch_frankfurter(base, quote, on) or _fetch_erapi(base, quote)
    if rate is None:
        return None
    DailyFxRate.objects.update_or_create(
        base=base,
        quote=quote,
        as_of=on,
        defaults={"rate": rate, "source": "live"},
    )
    return rate


def _fetch_frankfurter(base: str, quote: str, on: dt.date) -> Decimal | None:
    import requests

    url = f"{settings.FX_PROVIDER_PRIMARY}/{on.isoformat()}"
    try:
        resp = requests.get(url, params={"base": base, "symbols": quote}, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        value = data.get("rates", {}).get(quote)
        return Decimal(str(value)) if value is not None else None
    except (requests.RequestException, ValueError):
        return None


def _fetch_erapi(base: str, quote: str) -> Decimal | None:
    import requests

    url = f"{settings.FX_PROVIDER_FALLBACK}/latest/{base}"
    try:
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        value = data.get("rates", {}).get(quote)
        return Decimal(str(value)) if value is not None else None
    except (requests.RequestException, ValueError):
        return None
