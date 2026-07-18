"""Analytics API endpoints."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics import services
from apps.groups.models import Group
from apps.groups.permissions import is_group_member


class GroupAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        group_id = request.query_params.get("group")
        if not group_id:
            return Response({"detail": "group is required."}, status=status.HTTP_400_BAD_REQUEST)
        group = get_object_or_404(Group.objects.prefetch_related("expenses"), id=group_id)
        if not is_group_member(request.user, group.id):
            self.permission_denied(request, message="Not a group member.")
        return Response(services.group_analytics(group))


class PersonalAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.personal_analytics(request.user))


class CardAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.card_analytics(request.user))
