"""Splitwise import API."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations import services


class SplitwiseGroupsView(APIView):
    """POST {api_key} -> preview the Splitwise groups available to import."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_key = (request.data.get("api_key") or "").strip()
        if not api_key:
            return Response({"detail": "api_key is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            groups = services.list_splitwise_groups(api_key)
        except services.SplitwiseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"groups": groups})


class SplitwiseImportView(APIView):
    """POST {api_key, group_ids?} -> import selected groups' data."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_key = (request.data.get("api_key") or "").strip()
        if not api_key:
            return Response({"detail": "api_key is required."}, status=status.HTTP_400_BAD_REQUEST)
        group_ids = request.data.get("group_ids") or None
        try:
            result = services.import_from_splitwise(request.user, api_key, group_ids=group_ids)
        except services.SplitwiseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
