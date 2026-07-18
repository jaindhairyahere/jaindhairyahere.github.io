"""Server-side feature flag / entitlement resolution.

Everything is free by default. Flags in ``settings.FEATURE_FLAGS`` can be
flipped to ``False`` to gate a capability. This module is the single place
the rest of the code asks "is X allowed?".
"""
from __future__ import annotations

from django.conf import settings


def is_enabled(flag: str) -> bool:
    """Return whether a named feature flag is currently enabled."""
    return bool(settings.FEATURE_FLAGS.get(flag, False))


def all_flags() -> dict[str, bool]:
    """Return a copy of the resolved flag map (safe to serialize)."""
    return dict(settings.FEATURE_FLAGS)
