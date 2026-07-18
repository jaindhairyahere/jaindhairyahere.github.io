"""Splitwise migration.

Imports a user's Splitwise groups, members, categories, expenses and
settlements into this app using the Splitwise Self-Serve API. The API key is
used transiently and never persisted.

Note: Splitwise's API Terms prohibit building an app that competes with
Splitwise; this importer is intended for personal/internal migration only.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.expenses import services as expense_services
from apps.expenses.models import Category
from apps.groups.models import Group, GroupKind
from apps.members.models import Member, MemberRole

User = get_user_model()

SUPPORTED = {"INR", "USD", "EUR"}
BASE_URL = "https://secure.splitwise.com/api/v3.0"


class SplitwiseError(Exception):
    pass


class SplitwiseClient:
    """Thin client over the Splitwise API key auth."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _get(self, path: str, params: dict | None = None):
        import requests

        try:
            resp = requests.get(
                f"{BASE_URL}{path}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params=params or {},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise SplitwiseError(f"Network error contacting Splitwise: {exc}") from exc
        if resp.status_code == 401:
            raise SplitwiseError("Invalid Splitwise API key.")
        if not resp.ok:
            raise SplitwiseError(f"Splitwise API error {resp.status_code}.")
        return resp.json()

    def current_user(self):
        return self._get("/get_current_user")["user"]

    def categories(self):
        return self._get("/get_categories")["categories"]

    def groups(self):
        return self._get("/get_groups")["groups"]

    def expenses(self, group_id: int, limit: int = 100, offset: int = 0):
        return self._get(
            "/get_expenses", {"group_id": group_id, "limit": limit, "offset": offset}
        )["expenses"]


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError):
        return Decimal(0)


def _build_category_map(sw_categories) -> dict[int, Category]:
    """Map Splitwise (sub)category id -> our Category, via seeded name hints."""
    ours = list(Category.objects.all())
    other = next((c for c in ours if c.slug == "other"), None)

    def match(name: str):
        low = (name or "").lower()
        for c in ours:
            hints = [h.strip().lower() for h in (c.splitwise_names or "").split("|") if h.strip()]
            if c.name.lower() == low or low in hints or any(low in h or h in low for h in hints):
                return c
        return other

    mapping: dict[int, Category] = {}
    for parent in sw_categories:
        for sub in parent.get("subcategories", []) or []:
            mapping[sub["id"]] = match(parent.get("name")) or match(sub.get("name"))
        mapping[parent["id"]] = match(parent.get("name"))
    return mapping


def _resolve_members(group, sw_members) -> dict[int, Member]:
    """Create our Members for each Splitwise member; link by email when known."""
    mapping: dict[int, Member] = {}
    for m in sw_members:
        email = (m.get("email") or "").strip().lower()
        name = " ".join(filter(None, [m.get("first_name"), m.get("last_name")])) or email or "Member"
        user = User.objects.filter(email__iexact=email).first() if email else None
        existing = None
        if user:
            existing = group.members.filter(user=user).first()
        member = existing or Member.objects.create(
            group=group, user=user, display_name=name,
            role=MemberRole.OWNER if user else MemberRole.MEMBER,
        )
        mapping[m["id"]] = member
    return mapping


@transaction.atomic
def _import_group(user, client: SplitwiseClient, sw_group, cat_map) -> dict:
    # Infer a base currency from expenses; default INR.
    raw_expenses = client.expenses(sw_group["id"])
    currencies = [e.get("currency_code") for e in raw_expenses if e.get("currency_code") in SUPPORTED]
    base_currency = max(set(currencies), key=currencies.count) if currencies else "INR"

    group = Group.objects.create(
        name=sw_group.get("name", "Imported group"),
        kind=GroupKind.REGULAR,
        base_currency=base_currency,
        created_by=user,
    )
    member_map = _resolve_members(group, sw_group.get("members", []))
    # Guarantee the importing user is an owner member.
    if not group.members.filter(user=user).exists():
        Member.objects.create(
            group=group, user=user,
            display_name=user.get_full_name() or user.email, role=MemberRole.OWNER,
        )

    imported = skipped = settlements = 0
    for e in raw_expenses:
        if e.get("deleted_at"):
            continue
        currency = e.get("currency_code")
        if currency not in SUPPORTED:
            skipped += 1
            continue
        shares = e.get("users", [])
        payers = [
            {"member": member_map[u["user"]["id"]].id, "amount_paid": _dec(u.get("paid_share"))}
            for u in shares if member_map.get(u["user"]["id"]) and _dec(u.get("paid_share")) > 0
        ]
        splits = [
            {"member": member_map[u["user"]["id"]].id, "share_amount": _dec(u.get("owed_share"))}
            for u in shares if member_map.get(u["user"]["id"]) and _dec(u.get("owed_share")) > 0
        ]
        if not payers or not splits:
            skipped += 1
            continue

        if e.get("payment"):
            # A settlement: single payer -> single receiver.
            from apps.balances.models import Settlement

            try:
                Settlement.objects.create(
                    group=group, from_member_id=payers[0]["member"],
                    to_member_id=splits[0]["member"], amount=_dec(e.get("cost")),
                    currency=currency, date=(e.get("date") or "")[:10] or None,
                    note="Imported from Splitwise",
                )
                settlements += 1
            except Exception:
                skipped += 1
            continue

        category = cat_map.get(e.get("category_id"))
        try:
            expense_services.create_expense(
                user=user, group=group,
                description=e.get("description", "Imported"),
                currency=currency, total_amount=_dec(e.get("cost")),
                date=(e.get("date") or "")[:10],
                payers=payers, splits=splits,
                merchant="", payment_mode="other",
                category_id=category.id if category else None,
            )
            imported += 1
        except (ValidationError, Exception):
            skipped += 1

    return {
        "group": group.name, "group_id": group.id, "base_currency": base_currency,
        "imported": imported, "settlements": settlements, "skipped": skipped,
    }


def import_from_splitwise(user, api_key: str, group_ids=None, client: SplitwiseClient | None = None):
    client = client or SplitwiseClient(api_key)
    cat_map = _build_category_map(client.categories())
    all_groups = client.groups()
    selected = [
        g for g in all_groups
        if g.get("id") and g["id"] != 0 and (not group_ids or g["id"] in set(group_ids))
    ]
    return {"results": [_import_group(user, client, g, cat_map) for g in selected]}


def list_splitwise_groups(api_key: str):
    """Preview: list the user's Splitwise groups for selection."""
    client = SplitwiseClient(api_key)
    return [
        {"id": g["id"], "name": g.get("name"), "members": len(g.get("members", []))}
        for g in client.groups()
        if g.get("id") and g["id"] != 0
    ]
