"""Card + cashback API: CRUD, check-transaction preview, best-card suggestion."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cards import engine
from apps.cards.models import CashbackProgram, CreditCard, Wallet
from apps.cards.serializers import (
    CashbackProgramSerializer,
    CreditCardSerializer,
    WalletSerializer,
)
from apps.groups.models import Group
from apps.groups.permissions import is_group_member


def _member_group_ids(user):
    return Group.objects.filter(members__user=user, members__is_active=True).values_list(
        "id", flat=True
    )


class CreditCardViewSet(viewsets.ModelViewSet):
    serializer_class = CreditCardSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            CreditCard.objects.filter(group_id__in=_member_group_ids(self.request.user))
            .select_related("owner")
            .prefetch_related("programs")
        )

    def perform_create(self, serializer):
        group = serializer.validated_data["group"]
        if not is_group_member(self.request.user, group.id):
            self.permission_denied(self.request, message="Not a group member.")
        serializer.save()


class CashbackProgramViewSet(viewsets.ModelViewSet):
    serializer_class = CashbackProgramSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CashbackProgram.objects.filter(
            card__group_id__in=_member_group_ids(self.request.user)
        ).select_related("card")

    def perform_create(self, serializer):
        card = serializer.validated_data["card"]
        if not is_group_member(self.request.user, card.group_id):
            self.permission_denied(self.request, message="Not a group member.")
        serializer.save()


class WalletViewSet(viewsets.ModelViewSet):
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Wallet.objects.filter(
            group_id__in=_member_group_ids(self.request.user)
        ).select_related("owner")

    def perform_create(self, serializer):
        group = serializer.validated_data["group"]
        if not is_group_member(self.request.user, group.id):
            self.permission_denied(self.request, message="Not a group member.")
        serializer.save()


class CashbackCheckView(viewsets.ViewSet):
    """Preview cashback without recording anything."""

    permission_classes = [IsAuthenticated]

    def create(self, request):
        card_id = request.data.get("card")
        merchant = request.data.get("merchant", "")
        amount_raw = request.data.get("amount", "0")
        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, ValueError):
            return Response({"detail": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)
        card = CreditCard.objects.filter(id=card_id).select_related("group").first()
        if not card or not is_group_member(request.user, card.group_id):
            return Response({"detail": "Card not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(engine.quote(card, merchant, amount).as_dict())

    @action(detail=False, methods=["post"], url_path="best-card")
    def best(self, request):
        group_id = request.data.get("group")
        merchant = request.data.get("merchant", "")
        amount_raw = request.data.get("amount", "0")
        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, ValueError):
            return Response({"detail": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)
        group = Group.objects.filter(id=group_id).first()
        if not group or not is_group_member(request.user, group.id):
            return Response({"detail": "Group not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"ranked": engine.best_card(group, merchant, amount)})
