"""Object-level permission: only active members may access a group's data."""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.members.models import Member


def is_group_member(user, group_id) -> bool:
    if not user or not user.is_authenticated:
        return False
    return Member.objects.filter(group_id=group_id, user=user, is_active=True).exists()


class IsGroupMember(BasePermission):
    """Grants access when the request user is an active member of the object's group.

    Works for ``Group`` instances and any object exposing a ``group_id``.
    """

    def has_object_permission(self, request, view, obj):
        group_id = getattr(obj, "id", None) if obj.__class__.__name__ == "Group" else getattr(obj, "group_id", None)
        return is_group_member(request.user, group_id)
