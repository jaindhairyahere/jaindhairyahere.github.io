"""Core API: feature flags, supported currencies, FX conversion helpers."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import features, fx
from apps.core.enums import Currency


class FeatureFlagsView(APIView):
    """Expose resolved server-side feature flags to the client."""

    permission_classes = [IsAuthenticated]

    def get(self, _request):
        return Response(features.all_flags())


class CurrenciesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, _request):
        return Response(
            {
                "currencies": [
                    {"code": c.value, "label": c.label} for c in Currency
                ],
                "supported": settings.SUPPORTED_CURRENCIES,
            }
        )


class FxConvertView(APIView):
    """Preview a conversion between two supported currencies (today's rate)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not features.is_enabled("multi_currency"):
            return Response(
                {"detail": "Multi-currency is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        base = request.query_params.get("base", "").upper()
        quote = request.query_params.get("quote", "").upper()
        amount_raw = request.query_params.get("amount", "1")
        if base not in settings.SUPPORTED_CURRENCIES or quote not in settings.SUPPORTED_CURRENCIES:
            return Response(
                {"detail": "Unsupported currency."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, ValueError):
            return Response(
                {"detail": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            rate = fx.get_rate(base, quote)
            converted = fx.convert(amount, base, quote)
        except fx.FxError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(
            {
                "base": base,
                "quote": quote,
                "amount": str(amount),
                "rate": str(rate),
                "converted": str(converted),
            }
        )
