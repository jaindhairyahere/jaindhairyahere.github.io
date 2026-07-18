"""Balance engine: per-member nets, min-cash-flow simplification, settlements.

All amounts are computed in the group's base currency using each expense's
snapshotted ``fx_rate``. Cashback reduces what borrowers owe and what the
card owner is owed (they keep the cashback), keeping every expense balanced.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from apps.balances.models import Settlement
from apps.expenses.models import Expense

_CENTS = Decimal("0.01")
_EPS = Decimal("0.005")


def _q(v) -> Decimal:
    return Decimal(v).quantize(_CENTS, rounding=ROUND_HALF_UP)


def expense_member_nets(expense: Expense) -> dict[int, Decimal]:
    """Net (paid - owed) per member for one expense, in base currency."""
    fx = expense.fx_rate
    total = expense.total_amount
    cashback = expense.cashback_amount or Decimal(0)
    nets: dict[int, Decimal] = defaultdict(Decimal)

    for p in expense.payers.all():
        nets[p.member_id] += _q(p.amount_paid * fx)

    # Card owner keeps the cashback -> they are owed that much less.
    if expense.card_id and cashback > 0 and expense.card:
        nets[expense.card.owner_id] -= cashback

    for s in expense.splits.all():
        share_base = _q(s.share_amount * fx)
        cb_share = _q(cashback * (s.share_amount / total)) if total > 0 else Decimal(0)
        nets[s.member_id] -= (share_base - cb_share)

    return nets


def _combine(target: dict[int, Decimal], source: dict[int, Decimal], sign: int = 1) -> None:
    for k, v in source.items():
        target[k] += v * sign


def min_cash_flow(nets: dict[int, Decimal]) -> list[dict]:
    """Greedy minimum-cash-flow: settle nets with the fewest transactions."""
    creditors = [[m, a] for m, a in nets.items() if a > _EPS]
    debtors = [[m, -a] for m, a in nets.items() if a < -_EPS]
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    txns: list[dict] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        d, c = debtors[i], creditors[j]
        amt = _q(min(d[1], c[1]))
        if amt > 0:
            txns.append({"from_member": d[0], "to_member": c[0], "amount": str(amt)})
        d[1] -= amt
        c[1] -= amt
        if d[1] <= _EPS:
            i += 1
        if c[1] <= _EPS:
            j += 1
    return txns


def _edges_from_nets(nets: dict[int, Decimal]) -> list[dict]:
    """Direct pairwise edges for a single expense (its own minimal settlement)."""
    return min_cash_flow(nets)


def _net_edges(edges: list[tuple[int, int, Decimal]]) -> list[dict]:
    agg: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for d, c, a in edges:
        agg[(d, c)] += a
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for (d, c), a in agg.items():
        if (d, c) in seen:
            continue
        seen.add((d, c))
        seen.add((c, d))
        net = a - agg.get((c, d), Decimal(0))
        if net > _EPS:
            out.append({"from_member": d, "to_member": c, "amount": str(_q(net))})
        elif net < -_EPS:
            out.append({"from_member": c, "to_member": d, "amount": str(_q(-net))})
    return out


def group_summary(group) -> dict:
    """Full balance picture for a group.

    Returns per-member net balances (source of truth) plus a suggested list
    of settlement transactions. Non-overridden expenses follow the group's
    ``simplify_enabled`` setting; overridden expenses are always shown as
    direct debts.
    """
    expenses = list(
        Expense.objects.filter(group=group)
        .select_related("card", "card__owner")
        .prefetch_related("payers", "splits")
    )
    settlements = list(Settlement.objects.filter(group=group))

    all_nets: dict[int, Decimal] = defaultdict(Decimal)
    pool_nets: dict[int, Decimal] = defaultdict(Decimal)
    override_edges: list[tuple[int, int, Decimal]] = []

    for exp in expenses:
        nets = expense_member_nets(exp)
        _combine(all_nets, nets)
        if exp.simplify_override:
            for e in _edges_from_nets(nets):
                override_edges.append(
                    (e["from_member"], e["to_member"], Decimal(e["amount"]))
                )
        else:
            _combine(pool_nets, nets)

    # Settlements: payer's balance rises, receiver's falls.
    for s in settlements:
        all_nets[s.from_member_id] += s.amount
        all_nets[s.to_member_id] -= s.amount
        pool_nets[s.from_member_id] += s.amount
        pool_nets[s.to_member_id] -= s.amount

    if group.simplify_enabled:
        pool_txns = min_cash_flow(dict(pool_nets))
    else:
        pool_edges = []
        for exp in expenses:
            if exp.simplify_override:
                continue
            for e in _edges_from_nets(expense_member_nets(exp)):
                pool_edges.append((e["from_member"], e["to_member"], Decimal(e["amount"])))
        # Fold settlements in as cancelling edges.
        for s in settlements:
            pool_edges.append((s.to_member_id, s.from_member_id, s.amount))
        pool_txns = _net_edges(pool_edges)

    suggested = pool_txns + _net_edges(override_edges)

    # Member display names.
    names = {m.id: m.display_name for m in group.members.all()}
    balances = [
        {
            "member": mid,
            "member_name": names.get(mid, str(mid)),
            "net": str(_q(net)),  # positive = is owed; negative = owes
        }
        for mid, net in sorted(all_nets.items(), key=lambda kv: kv[1], reverse=True)
        if abs(net) > _EPS
    ]

    # Attach names to the suggested settlements.
    for t in suggested:
        t["from_name"] = names.get(t["from_member"], str(t["from_member"]))
        t["to_name"] = names.get(t["to_member"], str(t["to_member"]))

    return {
        "group": group.id,
        "base_currency": group.base_currency,
        "simplify_enabled": group.simplify_enabled,
        "balances": balances,
        "suggested_settlements": suggested,
    }
