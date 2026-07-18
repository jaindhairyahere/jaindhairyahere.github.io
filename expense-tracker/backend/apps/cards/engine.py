"""Cashback eligibility engine.

Given a card, merchant and amount (in the group base currency), computes how
much cashback would actually be granted, honoring the program's percentage,
per-transaction cap, amount caps and count ("vouch") caps across day / week /
month / year / lifetime windows. Reads the accrual ledger to know prior usage.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.cards.models import CashbackProgram, CreditCard

_CENTS = Decimal("0.01")


def _q(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(_CENTS, rounding=ROUND_DOWN)


@dataclass
class CashbackQuote:
    eligible: Decimal
    gross: Decimal
    program_id: int | None = None
    percent: Decimal = Decimal(0)
    capped_by: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "eligible": str(_q(self.eligible)),
            "gross": str(_q(self.gross)),
            "program_id": self.program_id,
            "percent": str(self.percent),
            "capped_by": self.capped_by,
            "reason": self.reason,
        }


def _window_bounds(on: dt.date):
    """Return (start_date, filter_kwargs) for each capped window."""
    start_week = on - dt.timedelta(days=on.weekday())
    return {
        "day": {"accrued_on": on},
        "week": {"accrued_on__gte": start_week, "accrued_on__lte": on},
        "month": {"accrued_on__year": on.year, "accrued_on__month": on.month},
        "year": {"accrued_on__year": on.year},
        "total": {},
    }


def _usage(card: CreditCard, program: CashbackProgram, flt: dict, exclude_expense_id=None):
    from apps.expenses.models import CashbackAccrual

    qs = CashbackAccrual.objects.filter(program=program, **flt)
    if exclude_expense_id is not None:
        qs = qs.exclude(expense_id=exclude_expense_id)
    agg = qs.aggregate(total=Sum("amount"), cnt=Count("id"))
    return (agg["total"] or Decimal(0)), (agg["cnt"] or 0)


def _match_programs(card: CreditCard, merchant: str):
    merchant = (merchant or "").strip()
    programs = card.programs.filter(is_active=True)
    matches = [
        p
        for p in programs
        if p.merchant == CashbackProgram.ANY_MERCHANT
        or (merchant and p.merchant.lower() == merchant.lower())
    ]
    # Prefer a specific merchant match over ANY, then higher percent.
    matches.sort(
        key=lambda p: (p.merchant != CashbackProgram.ANY_MERCHANT, p.percent), reverse=True
    )
    return matches


def quote_for_program(
    program: CashbackProgram, amount_base: Decimal, on: dt.date, exclude_expense_id=None
) -> CashbackQuote:
    """Compute the cashback a single program would grant for ``amount_base``."""
    amount_base = Decimal(amount_base)
    gross = _q(amount_base * program.percent / Decimal(100))
    eligible = gross
    capped_by: list[str] = []

    if program.max_per_txn is not None and eligible > program.max_per_txn:
        eligible = program.max_per_txn
        capped_by.append("per_txn")

    amount_caps = {
        "day": program.cap_per_day,
        "week": program.cap_per_week,
        "month": program.cap_per_month,
        "year": program.cap_per_year,
        "total": program.cap_total,
    }
    count_caps = {
        "day": program.max_per_day,
        "week": program.max_per_week,
        "month": program.max_per_month,
        "year": program.max_per_year,
        "total": program.max_vouches_total,
    }
    windows = _window_bounds(on)

    for name, flt in windows.items():
        used_amount, used_count = None, None

        cap = amount_caps.get(name)
        if cap is not None:
            used_amount, used_count = _usage(program.card, program, flt, exclude_expense_id)
            remaining = cap - used_amount
            if remaining <= 0:
                return CashbackQuote(
                    Decimal(0), gross, program.id, program.percent,
                    [f"{name}_amount"], f"{name} amount cap reached",
                )
            if eligible > remaining:
                eligible = remaining
                capped_by.append(f"{name}_amount")

        max_count = count_caps.get(name)
        if max_count is not None:
            if used_count is None:
                _, used_count = _usage(program.card, program, flt, exclude_expense_id)
            if used_count >= max_count:
                return CashbackQuote(
                    Decimal(0), gross, program.id, program.percent,
                    [f"{name}_count"], f"{name} vouch-count cap reached",
                )

    return CashbackQuote(_q(max(eligible, Decimal(0))), gross, program.id, program.percent, capped_by)


def quote(
    card: CreditCard, merchant: str, amount_base: Decimal, on: dt.date | None = None,
    exclude_expense_id=None,
) -> CashbackQuote:
    """Best cashback quote for a card+merchant+amount (base currency)."""
    on = on or timezone.localdate()
    programs = _match_programs(card, merchant)
    if not programs:
        return CashbackQuote(Decimal(0), Decimal(0), None, Decimal(0), [], "No matching program")
    best = None
    for program in programs:
        q = quote_for_program(program, amount_base, on, exclude_expense_id)
        if best is None or q.eligible > best.eligible:
            best = q
    return best


def best_card(group, merchant: str, amount_base: Decimal, on: dt.date | None = None):
    """Rank a group's active cards by the cashback they would grant."""
    on = on or timezone.localdate()
    results = []
    for card in group.cards.filter(is_active=True).prefetch_related("programs"):
        q = quote(card, merchant, amount_base, on)
        results.append(
            {
                "card_id": card.id,
                "card_name": card.display_name,
                "owner": card.owner.display_name,
                "eligible": str(_q(q.eligible)),
                "percent": str(q.percent),
                "capped_by": q.capped_by,
            }
        )
    results.sort(key=lambda r: Decimal(r["eligible"]), reverse=True)
    return results
