"""Expense domain service. All writes are atomic and validated."""
from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.cards import engine
from apps.cards.models import CreditCard
from apps.core import fx
from apps.expenses.models import (
    CashbackAccrual,
    CoinAccrual,
    Expense,
    ExpensePayer,
    ExpenseSplit,
)
from apps.members.models import Member

_CENTS = Decimal("0.01")


def _q(v) -> Decimal:
    return Decimal(str(v)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _resolve_cashback(card, merchant, base_amount, date, exclude_expense_id=None):
    """Return (cashback_amount_for_balances, program, eligible_cash).

    ``cashback_amount_for_balances`` is the cash value that reduces what
    borrowers owe (0 for coin payouts, which are a personal perk).
    """
    if not card:
        return Decimal(0), None, Decimal(0)
    q = engine.quote(card, merchant, base_amount, date, exclude_expense_id=exclude_expense_id)
    program = card.programs.filter(id=q.program_id).first() if q.program_id else None
    eligible = q.eligible
    if not program or eligible <= 0:
        return Decimal(0), program, Decimal(0)
    is_coins = program.payout == "coins" and program.wallet_id
    balance_effect = Decimal(0) if is_coins else eligible
    return balance_effect, program, eligible


def _record_accruals(expense, card, program, eligible_cash, date):
    """Persist cap-tracking + coin ledger rows after the expense exists."""
    if not program or eligible_cash <= 0:
        return
    # Always record for cap enforcement (cash-equivalent value + a vouch).
    CashbackAccrual.objects.create(
        expense=expense, program=program, card=card,
        amount=eligible_cash, currency=expense.group.base_currency, accrued_on=date,
    )
    if program.payout == "coins" and program.wallet_id:
        wallet = program.wallet
        rate = wallet.coin_rate or Decimal(1)
        coins = (eligible_cash / rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        expires_on = None
        if program.coin_expiry_days:
            expires_on = date + dt.timedelta(days=int(program.coin_expiry_days))
        CoinAccrual.objects.create(
            expense=expense, wallet=wallet, program=program, coins=coins,
            rate_at_award=rate, cash_value=eligible_cash, currency=wallet.currency,
            awarded_on=date, expires_on=expires_on,
        )


def _validate_members(group_id: int, member_ids: set[int]) -> dict[int, Member]:
    members = {m.id: m for m in Member.objects.filter(id__in=member_ids)}
    for mid in member_ids:
        if mid not in members or members[mid].group_id != group_id:
            raise ValidationError(f"Member {mid} does not belong to this group.")
    return members


def _validate_sums(total: Decimal, payers: list[dict], splits: list[dict]) -> None:
    paid = sum((_q(p["amount_paid"]) for p in payers), Decimal(0))
    owed = sum((_q(s["share_amount"]) for s in splits), Decimal(0))
    if paid != total:
        raise ValidationError(f"Payer amounts ({paid}) must sum to the total ({total}).")
    if owed != total:
        raise ValidationError(f"Split shares ({owed}) must sum to the total ({total}).")


@transaction.atomic
def create_expense(
    *,
    user,
    group,
    description: str,
    currency: str,
    total_amount,
    date: dt.date,
    payers: list[dict],
    splits: list[dict],
    merchant: str = "",
    payment_mode: str = "cash",
    card_id: int | None = None,
    simplify_override: bool = False,
    category_id: int | None = None,
) -> Expense:
    if currency not in settings.SUPPORTED_CURRENCIES:
        raise ValidationError("Unsupported currency.")
    if not payers or not splits:
        raise ValidationError("An expense needs at least one payer and one split.")

    total = _q(total_amount)
    _validate_sums(total, payers, splits)

    member_ids = {int(p["member"]) for p in payers} | {int(s["member"]) for s in splits}
    _validate_members(group.id, member_ids)

    # FX snapshot -> base currency.
    fx_rate = fx.get_rate(currency, group.base_currency, date)
    base_amount = fx.convert(total, currency, group.base_currency, date)

    card = None
    if card_id:
        card = CreditCard.objects.select_related("owner").filter(
            id=card_id, group_id=group.id
        ).first()
        if not card:
            raise ValidationError("Card not found in this group.")
        if card.owner_id not in {int(p["member"]) for p in payers}:
            raise ValidationError(
                "When paying with a card, the card owner must be a payer "
                "(they fronted the money and receive the cashback)."
            )
    cashback_amount, program, eligible_cash = _resolve_cashback(card, merchant, base_amount, date)

    expense = Expense.objects.create(
        group=group,
        description=description,
        category_id=category_id,
        currency=currency,
        total_amount=total,
        fx_rate=fx_rate,
        base_amount=base_amount,
        date=date,
        merchant=merchant,
        payment_mode=payment_mode,
        card=card,
        cashback_program=program,
        cashback_amount=cashback_amount,
        simplify_override=simplify_override,
        created_by=user,
    )

    ExpensePayer.objects.bulk_create(
        [ExpensePayer(expense=expense, member_id=int(p["member"]), amount_paid=_q(p["amount_paid"]))
         for p in payers]
    )
    ExpenseSplit.objects.bulk_create(
        [ExpenseSplit(expense=expense, member_id=int(s["member"]), share_amount=_q(s["share_amount"]),
                      split_type=s.get("split_type", "equal")) for s in splits]
    )
    _record_accruals(expense, card, program, eligible_cash, date)
    return expense


@transaction.atomic
def update_expense(*, expense: Expense, user, **fields) -> Expense:
    """Replace an expense's payers/splits and recompute FX + cashback."""
    group = expense.group
    payers = fields["payers"]
    splits = fields["splits"]
    currency = fields.get("currency", expense.currency)
    if currency not in settings.SUPPORTED_CURRENCIES:
        raise ValidationError("Unsupported currency.")

    total = _q(fields.get("total_amount", expense.total_amount))
    _validate_sums(total, payers, splits)
    member_ids = {int(p["member"]) for p in payers} | {int(s["member"]) for s in splits}
    _validate_members(group.id, member_ids)

    date = fields.get("date", expense.date)
    merchant = fields.get("merchant", expense.merchant)
    card_id = fields.get("card_id", expense.card_id)

    fx_rate = fx.get_rate(currency, group.base_currency, date)
    base_amount = fx.convert(total, currency, group.base_currency, date)

    # Reset children + accruals so caps recompute cleanly.
    expense.payers.all().delete()
    expense.splits.all().delete()
    CashbackAccrual.objects.filter(expense=expense).delete()
    CoinAccrual.objects.filter(expense=expense).delete()

    card = None
    if card_id:
        card = CreditCard.objects.select_related("owner").filter(
            id=card_id, group_id=group.id
        ).first()
        if not card:
            raise ValidationError("Card not found in this group.")
        if card.owner_id not in {int(p["member"]) for p in payers}:
            raise ValidationError("The card owner must be a payer.")
    cashback_amount, program, eligible_cash = _resolve_cashback(
        card, merchant, base_amount, date, exclude_expense_id=expense.id
    )

    expense.description = fields.get("description", expense.description)
    if "category_id" in fields:
        expense.category_id = fields["category_id"]
    expense.currency = currency
    expense.total_amount = total
    expense.fx_rate = fx_rate
    expense.base_amount = base_amount
    expense.date = date
    expense.merchant = merchant
    expense.payment_mode = fields.get("payment_mode", expense.payment_mode)
    expense.card = card
    expense.cashback_program = program
    expense.cashback_amount = cashback_amount
    expense.simplify_override = fields.get("simplify_override", expense.simplify_override)
    expense.save()

    ExpensePayer.objects.bulk_create(
        [ExpensePayer(expense=expense, member_id=int(p["member"]), amount_paid=_q(p["amount_paid"]))
         for p in payers]
    )
    ExpenseSplit.objects.bulk_create(
        [ExpenseSplit(expense=expense, member_id=int(s["member"]), share_amount=_q(s["share_amount"]),
                      split_type=s.get("split_type", "equal")) for s in splits]
    )
    _record_accruals(expense, card, program, eligible_cash, date)
    return expense


def equal_split(total, member_ids: list[int]) -> list[dict]:
    """Helper: split ``total`` equally, distributing the rounding remainder."""
    total = _q(total)
    n = len(member_ids)
    base = _q(total / n)
    shares = [base] * n
    remainder = total - base * n
    i = 0
    step = _CENTS if remainder > 0 else -_CENTS
    while remainder != 0:
        shares[i % n] += step
        remainder -= step
        i += 1
    return [{"member": mid, "share_amount": shares[idx], "split_type": "equal"}
            for idx, mid in enumerate(member_ids)]
