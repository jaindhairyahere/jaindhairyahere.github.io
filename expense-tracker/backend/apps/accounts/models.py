"""Accounts models: custom user + profile/entitlement holder."""
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.base_models import TimeStampedModel


class User(AbstractUser):
    """Custom user. Email is the primary identity (Google-provided)."""

    email = models.EmailField(unique=True)

    def __str__(self) -> str:
        return self.get_full_name() or self.username or self.email


class Plan(models.TextChoices):
    FREE = "free", "Free"
    PREMIUM = "premium", "Premium"


class Profile(TimeStampedModel):
    """Per-user profile holding the (optional) entitlement plan.

    Feature availability is resolved globally via ``apps.core.features``;
    this plan exists so gating can later be made per-user if desired.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=150, blank=True)
    avatar_url = models.URLField(blank=True)
    plan = models.CharField(max_length=16, choices=Plan.choices, default=Plan.FREE)

    def __str__(self) -> str:
        return f"Profile<{self.user}>"
