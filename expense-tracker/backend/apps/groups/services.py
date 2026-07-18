"""Group/member domain services. All mutations are atomic."""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.core import features
from apps.groups.models import Group, GroupKind
from apps.members.models import Member, MemberRole


def _friend_key(user_id_a: int, user_id_b: int) -> str:
    lo, hi = sorted((user_id_a, user_id_b))
    return f"u{lo}:u{hi}"


def _enforce_group_quota(user) -> None:
    """Block group creation past the free limit when the flag is off."""
    if features.is_enabled("unlimited_groups"):
        return
    count = Member.objects.filter(user=user, is_active=True).values("group").distinct().count()
    if count >= settings.FREE_GROUP_LIMIT:
        raise PermissionDenied(
            f"Free plan is limited to {settings.FREE_GROUP_LIMIT} groups."
        )


@transaction.atomic
def create_regular_group(*, creator, name: str, base_currency: str, simplify_enabled: bool = True) -> Group:
    _enforce_group_quota(creator)
    group = Group.objects.create(
        name=name,
        kind=GroupKind.REGULAR,
        base_currency=base_currency,
        simplify_enabled=simplify_enabled,
        created_by=creator,
    )
    Member.objects.create(
        group=group,
        user=creator,
        display_name=creator.get_full_name() or creator.email,
        role=MemberRole.OWNER,
    )
    return group


@transaction.atomic
def get_or_create_friend_group(
    *, creator, other_user=None, other_name: str | None = None, base_currency: str | None = None
) -> Group:
    """Return the unique friend group between ``creator`` and the other party.

    - Registered other user -> unique per unordered pair (idempotent).
    - Placeholder (name only) -> a new friend group each call (no global id).
    """
    base_currency = base_currency or "INR"

    if other_user is not None:
        if other_user.id == creator.id:
            raise ValidationError("Cannot create a friend group with yourself.")
        key = _friend_key(creator.id, other_user.id)
        existing = Group.objects.filter(friend_key=key).first()
        if existing:
            return existing
        _enforce_group_quota(creator)
        group = Group.objects.create(
            name=f"{creator.get_full_name() or creator.email} & "
            f"{other_user.get_full_name() or other_user.email}",
            kind=GroupKind.FRIEND,
            base_currency=base_currency,
            friend_key=key,
            created_by=creator,
        )
        Member.objects.create(
            group=group, user=creator,
            display_name=creator.get_full_name() or creator.email, role=MemberRole.OWNER,
        )
        Member.objects.create(
            group=group, user=other_user,
            display_name=other_user.get_full_name() or other_user.email, role=MemberRole.MEMBER,
        )
        return group

    if not other_name:
        raise ValidationError("Provide either other_user or other_name.")

    _enforce_group_quota(creator)
    group = Group.objects.create(
        name=f"{creator.get_full_name() or creator.email} & {other_name}",
        kind=GroupKind.FRIEND,
        base_currency=base_currency,
        created_by=creator,
    )
    Member.objects.create(
        group=group, user=creator,
        display_name=creator.get_full_name() or creator.email, role=MemberRole.OWNER,
    )
    Member.objects.create(group=group, display_name=other_name, role=MemberRole.MEMBER)
    return group


def assert_can_delete_group(group: Group) -> None:
    if group.is_friend:
        raise PermissionDenied("Friend groups cannot be deleted.")


def assert_can_remove_member(group: Group) -> None:
    if group.is_friend:
        raise PermissionDenied("Members cannot be removed from a friend group.")
