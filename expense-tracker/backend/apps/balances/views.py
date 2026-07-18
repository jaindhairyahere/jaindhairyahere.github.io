"""Balances + settlements API."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.balances import engine
from apps.balances.models import Settlement
from apps.balances.serializers import SettlementSerializer
from apps.groups.models import Group
from apps.groups.permissions import is_group_member


def _member_group_ids(user):
    return Group.objects.filter(members__user=user, members__is_active=True).values_list(
        "id", flat=True
    )


class SettlementViewSet(viewsets.ModelViewSet):
    serializer_class = SettlementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Settlement.objects.filter(
            group_id__in=_member_group_ids(self.request.user)
        ).select_related("from_member", "to_member")
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs

    def perform_create(self, serializer):
        group = serializer.validated_data["group"]
        if not is_group_member(self.request.user, group.id):
            self.permission_denied(self.request, message="Not a group member.")
        serializer.save(created_by=self.request.user)


class BalanceView(APIView):
    """GET /api/v1/balances/?group=<id> -> full balance summary."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        group_id = request.query_params.get("group")
        if not group_id:
            return Response({"detail": "group is required."}, status=status.HTTP_400_BAD_REQUEST)
        group = get_object_or_404(Group.objects.prefetch_related("members"), id=group_id)
        if not is_group_member(request.user, group.id):
            self.permission_denied(request, message="Not a group member.")
        return Response(engine.group_summary(group))
