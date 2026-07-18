"""Member: a participant within a group.

A member may be backed by a registered ``User`` or be a name-only
placeholder that can be linked to a real user later.
"""
from django.conf import settings
from django.db import models

from apps.core.base_models import TimeStampedModel


class MemberRole(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    MEMBER = "member", "Member"


class Member(TimeStampedModel):
    group = models.ForeignKey("groups.Group", on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships",
    )
    display_name = models.CharField(max_length=150)
    role = models.CharField(max_length=16, choices=MemberRole.choices, default=MemberRole.MEMBER)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_name"]
        constraints = [
            # A given user can appear at most once per group.
            models.UniqueConstraint(
                fields=["group", "user"],
                condition=models.Q(user__isnull=False),
                name="uniq_group_user",
            )
        ]
        indexes = [models.Index(fields=["group", "is_active"])]

    def __str__(self) -> str:
        return self.display_name

    @property
    def is_placeholder(self) -> bool:
        return self.user_id is None

