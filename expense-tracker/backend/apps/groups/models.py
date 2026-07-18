"""Group models: regular groups and special 2-person 'friend' groups."""
from django.conf import settings
from django.db import models

from apps.core.base_models import TimeStampedModel
from apps.core.enums import Currency


class GroupKind(models.TextChoices):
    REGULAR = "regular", "Regular"
    FRIEND = "friend", "Friend"


class Group(TimeStampedModel):
    """A collection of members that share expenses.

    A ``friend`` group is a special case: exactly two members, unique per
    unordered pair (enforced via ``friend_key`` for registered users), and
    it cannot be left or deleted.
    """

    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=16, choices=GroupKind.choices, default=GroupKind.REGULAR)
    base_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.INR)
    simplify_enabled = models.BooleanField(default=True)
    # Canonical key for registered-user friend pairs, e.g. "u3:u7". Null for
    # regular groups and for placeholder-based friend groups.
    friend_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_groups",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"

    @property
    def is_friend(self) -> bool:
        return self.kind == GroupKind.FRIEND
