"""Reusable abstract base models."""
from django.db import models


class TimeStampedModel(models.Model):
    """Adds created/updated audit timestamps to any model."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
