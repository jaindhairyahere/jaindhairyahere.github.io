"""Analytics aggregations for dashboards and charts.

Personal/cross-group figures are reported in a single currency (INR) using
cached daily FX so mixed-currency groups still sum sensibly. Group figures
use the group's own base currency.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.cards.models import CreditCard, Wallet
from apps.core import fx
from apps.expenses.models import CoinAccrual, Expense
from apps.groups.models import Group

REPORT_CCY = "INR"
_CENTS = Decimal("0.01")


def _q(v) -> Decimal:
    return Decimal(v).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _to_report(amount: Decimal, currency: str, on: dt.date) -> Decimal:
    """Convert to the reporting currency, degrading gracefully if FX is down."""
    if currency == REPORT_CCY:
        return Decimal(amount)
    try:
        return fx.convert(Decimal(amount), currency, REPORT_CCY, on)
    except Exception:
        return Decimal(amount)  # best-effort fallback


def _member_group_ids(user):
    return list(
        Group.objects.filter(members__user=user, members__is_active=True)
        .values_list("id", flat=True)
        .distinct()
    )


def _month_key(d: dt.date) -> str:
    return d.strftime("%Y-%m")


# ── Per-group analytics (group base currency) ───────────────────────────
def group_analytics(group) -> dict:
    expenses = list(
        group.expenses.select_related("category").prefetch_related("splits")
    )
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    by_month: dict[str, Decimal] = defaultdict(Decimal)
    by_merchant: dict[str, Decimal] = defaultdict(Decimal)
    total = Decimal(0)
    cashback = Decimal(0)

    for e in expenses:
        base = e.base_amount or Decimal(0)
        total += base
        cashback += e.cashback_amount or Decimal(0)
        cat = e.category.name if e.category else "Uncategorized"
        icon = e.category.icon if e.category else "❓"
        by_category[f"{icon}|{cat}"] += base
        by_month[_month_key(e.date)] += base
        if e.merchant:
            by_merchant[e.merchant] += base

    return {
        "group": group.id,
        "currency": group.base_currency,
        "total_spend": str(_q(total)),
        "total_cashback": str(_q(cashback)),
        "expense_count": len(expenses),
        "by_category": _cat_list(by_category),
        "by_month": _month_series(by_month),
        "top_merchants": _top(by_merchant, 5),
    }


# ── Personal cross-group analytics (reporting currency) ─────────────────
def personal_analytics(user) -> dict:
    group_ids = _member_group_ids(user)
    expenses = (
        Expense.objects.filter(group_id__in=group_ids)
        .select_related("category", "group")
        .prefetch_related("splits__member")
    )
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    by_month: dict[str, Decimal] = defaultdict(Decimal)
    total_my_share = Decimal(0)

    for e in expenses:
        if not e.total_amount:
            continue
        for s in e.splits.all():
            if s.member.user_id != user.id:
                continue
            # My base-currency share of this expense.
            base_share = (e.base_amount or Decimal(0)) * (s.share_amount / e.total_amount)
            report = _to_report(base_share, e.group.base_currency, e.date)
            total_my_share += report
            cat = e.category.name if e.category else "Uncategorized"
            icon = e.category.icon if e.category else "❓"
            by_category[f"{icon}|{cat}"] += report
            by_month[_month_key(e.date)] += report

    return {
        "currency": REPORT_CCY,
        "total_my_spend": str(_q(total_my_share)),
        "by_category": _cat_list(by_category),
        "by_month": _month_series(by_month),
    }


# ── Card & wallet usage analytics (reporting currency) ──────────────────
def card_analytics(user) -> dict:
    group_ids = _member_group_ids(user)

    my_cards = CreditCard.objects.filter(
        group_id__in=group_ids, owner__user=user
    ).select_related("owner")
    my_card_ids = list(my_cards.values_list("id", flat=True))

    # Expenses paid on MY cards (how friends used my cards).
    my_cards_used: dict[int, dict] = {
        c.id: {"card_id": c.id, "card_name": c.display_name, "spend": Decimal(0),
               "cashback_earned": Decimal(0), "coins_value": Decimal(0),
               "used_by": defaultdict(Decimal), "count": 0}
        for c in my_cards
    }
    for e in (
        Expense.objects.filter(card_id__in=my_card_ids)
        .select_related("group", "cashback_program", "cashback_program__wallet")
        .prefetch_related("splits__member")
    ):
        rec = my_cards_used[e.card_id]
        rec["count"] += 1
        rec["spend"] += _to_report(e.base_amount or Decimal(0), e.group.base_currency, e.date)
        rec["cashback_earned"] += _to_report(e.cashback_amount or Decimal(0), e.group.base_currency, e.date)
        for s in e.splits.all():
            if e.total_amount:
                share = (e.base_amount or Decimal(0)) * (s.share_amount / e.total_amount)
                rec["used_by"][s.member.display_name] += _to_report(share, e.group.base_currency, e.date)

    # Expenses where I owe a share on a FRIEND's card (how I used friends' cards).
    friends_cards: dict[int, dict] = {}
    for e in (
        Expense.objects.filter(group_id__in=group_ids, card__isnull=False)
        .exclude(card__owner__user=user)
        .select_related("group", "card", "card__owner")
        .prefetch_related("splits__member")
    ):
        my_share = Decimal(0)
        for s in e.splits.all():
            if s.member.user_id == user.id and e.total_amount:
                my_share += e.base_amount * (s.share_amount / e.total_amount)
        if my_share <= 0:
            continue
        cb_benefit = Decimal(0)
        if e.total_amount and e.cashback_amount:
            # My proportional cash cashback saving (coins don't benefit me).
            my_owed = sum(
                (s.share_amount for s in e.splits.all() if s.member.user_id == user.id), Decimal(0)
            )
            cb_benefit = e.cashback_amount * (my_owed / e.total_amount)
        key = e.card_id
        rec = friends_cards.setdefault(
            key, {"card_id": e.card_id, "card_name": e.card.display_name,
                   "owner": e.card.owner.display_name, "my_spend": Decimal(0),
                   "my_cashback_benefit": Decimal(0), "count": 0}
        )
        rec["count"] += 1
        rec["my_spend"] += _to_report(my_share, e.group.base_currency, e.date)
        rec["my_cashback_benefit"] += _to_report(cb_benefit, e.group.base_currency, e.date)

    return {
        "currency": REPORT_CCY,
        "my_cards": [_finalize_my_card(r) for r in my_cards_used.values()],
        "friends_cards": [_finalize_friend_card(r) for r in friends_cards.values()],
        "wallets": wallet_benefits(user),
    }


def wallet_benefits(user) -> list[dict]:
    """Unexpired coin value per wallet the user owns, plus expiring-soon."""
    from django.db.models import Q

    today = timezone.localdate()
    soon = today + dt.timedelta(days=30)
    group_ids = _member_group_ids(user)
    unexpired = Q(expires_on__isnull=True) | Q(expires_on__gte=today)
    out = []
    for w in Wallet.objects.filter(group_id__in=group_ids, owner__user=user):
        active = list(CoinAccrual.objects.filter(unexpired, wallet=w))
        coins = sum((a.coins for a in active), Decimal(0))
        expiring = sum(
            (a.coins for a in active if a.expires_on and a.expires_on <= soon), Decimal(0)
        )
        value = coins * (w.coin_rate or Decimal(1))
        out.append({
            "wallet_id": w.id, "name": w.name, "owner": w.owner.display_name,
            "coins": str(coins.quantize(Decimal("0.0001"))),
            "coin_rate": str(w.coin_rate), "currency": w.currency,
            "value": str(_q(value)),
            "expiring_soon_coins": str(expiring.quantize(Decimal("0.0001"))),
        })
    return out


# ── Formatting helpers ──────────────────────────────────────────────────
def _cat_list(d):
    items = []
    for k, v in d.items():
        icon, name = k.split("|", 1)
        items.append({"category": name, "icon": icon, "amount": str(_q(v))})
    items.sort(key=lambda x: Decimal(x["amount"]), reverse=True)
    return items


def _month_series(d):
    return [{"month": k, "amount": str(_q(v))} for k, v in sorted(d.items())]


def _top(d, n):
    items = [{"name": k, "amount": str(_q(v))} for k, v in d.items()]
    items.sort(key=lambda x: Decimal(x["amount"]), reverse=True)
    return items[:n]


def _finalize_my_card(r):
    used_by = [{"name": k, "amount": str(_q(v))} for k, v in r["used_by"].items()]
    used_by.sort(key=lambda x: Decimal(x["amount"]), reverse=True)
    return {
        "card_id": r["card_id"], "card_name": r["card_name"], "count": r["count"],
        "spend": str(_q(r["spend"])), "cashback_earned": str(_q(r["cashback_earned"])),
        "used_by": used_by,
    }


def _finalize_friend_card(r):
    return {
        "card_id": r["card_id"], "card_name": r["card_name"], "owner": r["owner"],
        "count": r["count"], "my_spend": str(_q(r["my_spend"])),
        "my_cashback_benefit": str(_q(r["my_cashback_benefit"])),
    }
