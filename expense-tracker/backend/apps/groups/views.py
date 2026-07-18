"""Group + member management API."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.groups import services
from apps.groups.models import Group
from apps.groups.permissions import IsGroupMember, is_group_member
from apps.groups.serializers import (
    CreateFriendGroupSerializer,
    CreateGroupSerializer,
    GroupSerializer,
)
from apps.members.models import Member, MemberRole
from apps.members.serializers import AddMemberSerializer, MemberSerializer

User = get_user_model()


class GroupViewSet(viewsets.ModelViewSet):
    """CRUD for groups the requesting user belongs to."""

    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated, IsGroupMember]

    def get_queryset(self):
        return (
            Group.objects.filter(members__user=self.request.user, members__is_active=True)
            .distinct()
            .prefetch_related("members", "members__user")
        )

    def create(self, request, *args, **kwargs):
        serializer = CreateGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = services.create_regular_group(creator=request.user, **serializer.validated_data)
        return Response(GroupSerializer(group).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        services.assert_can_delete_group(instance)
        instance.delete()

    @action(detail=False, methods=["post"])
    def friend(self, request):
        """Get or create the unique friend group with another person."""
        serializer = CreateFriendGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        other_user = None
        if data.get("email"):
            other_user = User.objects.filter(email__iexact=data["email"]).first()
        group = services.get_or_create_friend_group(
            creator=request.user,
            other_user=other_user,
            other_name=None if other_user else data.get("other_name"),
            base_currency=data["base_currency"],
        )
        return Response(GroupSerializer(group).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        group = self.get_object()
        if request.method == "GET":
            qs = group.members.select_related("user").all()
            return Response(MemberSerializer(qs, many=True).data)

        # POST: add a member (friend groups are fixed at 2).
        if group.is_friend:
            return Response(
                {"detail": "Friend groups have a fixed pair of members."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = AddMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
        display_name = serializer.validated_data.get("display_name")
        user = User.objects.filter(email__iexact=email).first() if email else None
        if user and group.members.filter(user=user).exists():
            return Response(
                {"detail": "User is already a member."}, status=status.HTTP_400_BAD_REQUEST
            )
        member = Member.objects.create(
            group=group,
            user=user,
            display_name=display_name or (user.get_full_name() or user.email if user else "Member"),
            role=MemberRole.MEMBER,
        )
        return Response(MemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="simplify")
    def toggle_simplify(self, request, pk=None):
        group = self.get_object()
        enabled = bool(request.data.get("simplify_enabled", not group.simplify_enabled))
        group.simplify_enabled = enabled
        group.save(update_fields=["simplify_enabled", "updated_at"])
        return Response(GroupSerializer(group).data)


class MemberViewSet(viewsets.ViewSet):
    """Update or remove individual members, or link a placeholder to a user."""

    permission_classes = [IsAuthenticated]

    def _get_member(self, request, pk) -> Member:
        member = get_object_or_404(Member.objects.select_related("group", "user"), pk=pk)
        if not is_group_member(request.user, member.group_id):
            self.permission_denied(request, message="Not a group member.")
        return member

    def partial_update(self, request, pk=None):
        member = self._get_member(request, pk)
        if "display_name" in request.data:
            member.display_name = request.data["display_name"]
        if "role" in request.data and request.data["role"] in MemberRole.values:
            member.role = request.data["role"]
        member.save()
        return Response(MemberSerializer(member).data)

    def destroy(self, request, pk=None):
        member = self._get_member(request, pk)
        services.assert_can_remove_member(member.group)
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="link")
    def link_user(self, request, pk=None):
        """Link a placeholder member to a registered user by email."""
        member = self._get_member(request, pk)
        if not member.is_placeholder:
            return Response(
                {"detail": "Member is already linked to a user."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = request.data.get("email", "")
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"detail": "No user with that email."}, status=status.HTTP_404_NOT_FOUND)
        if member.group.members.filter(user=user).exists():
            return Response(
                {"detail": "That user is already a member."}, status=status.HTTP_400_BAD_REQUEST
            )
        member.user = user
        member.save(update_fields=["user", "updated_at"])
        return Response(MemberSerializer(member).data)
