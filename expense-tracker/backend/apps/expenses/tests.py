"""Integration tests for the core money flows: expenses, cashback, balances.

These exercise the engines end-to-end (the parts most worth protecting).
"""
import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.balances import engine as balances_engine
from apps.balances.models import Settlement
from apps.cards import engine as cashback_engine
from apps.cards.models import CashbackProgram, CreditCard
from apps.core.models import DailyFxRate
from apps.expenses import services
from apps.groups import services as group_services
from apps.groups.models import Group
from apps.members.models import Member

User = get_user_model()
TODAY = dt.date(2026, 7, 18)


class BaseSetup(TestCase):
    def setUp(self):
        self.me = User.objects.create(username="me", email="me@example.com", first_name="Me")
        self.group = group_services.create_regular_group(
            creator=self.me, name="Flat", base_currency="INR"
        )
        self.m_me = self.group.members.get(user=self.me)
        self.m_ritik = Member.objects.create(group=self.group, display_name="Ritik")

    def _expense(self, **kw):
        defaults = dict(
            user=self.me, group=self.group, description="Test", currency="INR",
            date=TODAY, merchant="Swiggy", payment_mode="cash",
        )
        defaults.update(kw)
        return services.create_expense(**defaults)


class EqualSplitTests(BaseSetup):
    def test_equal_split_balances(self):
        exp = self._expense(
            total_amount="100.00",
            payers=[{"member": self.m_me.id, "amount_paid": "100.00"}],
            splits=services.equal_split("100.00", [self.m_me.id, self.m_ritik.id]),
        )
        self.assertEqual(exp.base_amount, Decimal("100.00"))
        summary = balances_engine.group_summary(self.group)
        nets = {b["member_name"]: Decimal(b["net"]) for b in summary["balances"]}
        self.assertEqual(nets["Me"], Decimal("50.00"))
        self.assertEqual(nets["Ritik"], Decimal("-50.00"))
        txns = summary["suggested_settlements"]
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0]["from_name"], "Ritik")
        self.assertEqual(txns[0]["to_name"], "Me")
        self.assertEqual(Decimal(txns[0]["amount"]), Decimal("50.00"))


class CashbackTests(BaseSetup):
    def _card(self, percent="10.00", **caps):
        card = CreditCard.objects.create(
            group=self.group, owner=self.m_ritik, display_name="Swiggy HDFC", issuer="HDFC"
        )
        CashbackProgram.objects.create(
            card=card, merchant="Swiggy", percent=Decimal(percent), currency="INR", **caps
        )
        return card

    def test_cashback_reduces_what_i_owe_ritik(self):
        """Spend 100 on Ritik's 10% card, all consumed by me -> I owe 90."""
        card = self._card("10.00")
        exp = self._expense(
            total_amount="100.00", payment_mode="card", card_id=card.id,
            payers=[{"member": self.m_ritik.id, "amount_paid": "100.00"}],
            splits=[{"member": self.m_me.id, "share_amount": "100.00"}],
        )
        self.assertEqual(exp.cashback_amount, Decimal("10.00"))
        summary = balances_engine.group_summary(self.group)
        nets = {b["member_name"]: Decimal(b["net"]) for b in summary["balances"]}
        self.assertEqual(nets["Me"], Decimal("-90.00"))
        self.assertEqual(nets["Ritik"], Decimal("90.00"))

    def test_cashback_per_txn_cap(self):
        card = self._card("10.00", max_per_txn=Decimal("5.00"))
        exp = self._expense(
            total_amount="100.00", payment_mode="card", card_id=card.id,
            payers=[{"member": self.m_ritik.id, "amount_paid": "100.00"}],
            splits=[{"member": self.m_me.id, "share_amount": "100.00"}],
        )
        self.assertEqual(exp.cashback_amount, Decimal("5.00"))

    def test_cashback_count_cap_blocks_second_same_day(self):
        card = self._card("10.00", max_per_day=1)
        first = self._expense(
            total_amount="100.00", payment_mode="card", card_id=card.id,
            payers=[{"member": self.m_ritik.id, "amount_paid": "100.00"}],
            splits=[{"member": self.m_me.id, "share_amount": "100.00"}],
        )
        second = self._expense(
            total_amount="100.00", payment_mode="card", card_id=card.id,
            payers=[{"member": self.m_ritik.id, "amount_paid": "100.00"}],
            splits=[{"member": self.m_me.id, "share_amount": "100.00"}],
        )
        self.assertEqual(first.cashback_amount, Decimal("10.00"))
        self.assertEqual(second.cashback_amount, Decimal("0.00"))

    def test_card_owner_must_be_payer(self):
        card = self._card("10.00")
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self._expense(
                total_amount="100.00", payment_mode="card", card_id=card.id,
                payers=[{"member": self.m_me.id, "amount_paid": "100.00"}],
                splits=[{"member": self.m_me.id, "share_amount": "100.00"}],
            )

    def test_best_card_ranks_by_cashback(self):
        self._card("10.00")  # Swiggy HDFC: 10% on Swiggy
        low_card = CreditCard.objects.create(
            group=self.group, owner=self.m_ritik, display_name="Amex Gold"
        )
        CashbackProgram.objects.create(
            card=low_card, merchant="ANY", percent=Decimal("8.00"), currency="INR"
        )
        ranked = cashback_engine.best_card(self.group, "Swiggy", Decimal("100.00"))
        self.assertEqual(ranked[0]["card_name"], "Swiggy HDFC")  # 10% specific match beats 8% ANY
        self.assertGreaterEqual(Decimal(ranked[0]["eligible"]), Decimal(ranked[1]["eligible"]))

    def test_coin_payout_does_not_reduce_debt(self):
        """Coin cashback is a personal perk: borrower still owes the full share."""
        from apps.cards.models import Wallet
        from apps.expenses.models import CoinAccrual

        card = CreditCard.objects.create(
            group=self.group, owner=self.m_ritik, display_name="Flipkart Axis"
        )
        wallet = Wallet.objects.create(
            group=self.group, owner=self.m_ritik, name="Flipkart Coins",
            coin_rate=Decimal("0.25"), currency="INR",
        )
        CashbackProgram.objects.create(
            card=card, merchant="ANY", percent=Decimal("10.00"), currency="INR",
            payout="coins", wallet=wallet, coin_expiry_days=365,
        )
        exp = self._expense(
            total_amount="100.00", payment_mode="card", card_id=card.id,
            payers=[{"member": self.m_ritik.id, "amount_paid": "100.00"}],
            splits=[{"member": self.m_me.id, "share_amount": "100.00"}],
        )
        self.assertEqual(exp.cashback_amount, Decimal("0.00"))  # no balance effect
        accrual = CoinAccrual.objects.get(expense=exp)
        self.assertEqual(accrual.coins, Decimal("40.0000"))  # 10 / 0.25
        summary = balances_engine.group_summary(self.group)
        nets = {b["member_name"]: Decimal(b["net"]) for b in summary["balances"]}
        self.assertEqual(nets["Me"], Decimal("-100.00"))  # still owes full amount


class SplitwiseImportTests(BaseSetup):
    def test_import_creates_group_and_expenses(self):
        from apps.integrations import services

        class FakeClient:
            def categories(self):
                return [{"id": 1, "name": "Food and drink",
                         "subcategories": [{"id": 12, "name": "Dining out"}]}]

            def current_user(self):
                return {"id": 99, "email": "me@example.com"}

            def groups(self):
                return [{"id": 500, "name": "Trip SW", "members": [
                    {"id": 99, "email": "me@example.com", "first_name": "Me"},
                    {"id": 77, "email": "", "first_name": "Zoya"},
                ]}]

            def expenses(self, group_id, limit=100, offset=0):
                return [{
                    "id": 1, "cost": "100.00", "description": "SW Dinner",
                    "currency_code": "INR", "category_id": 12, "date": "2026-07-10T00:00:00Z",
                    "payment": False, "deleted_at": None,
                    "users": [
                        {"user": {"id": 99}, "paid_share": "100.00", "owed_share": "50.00"},
                        {"user": {"id": 77}, "paid_share": "0.00", "owed_share": "50.00"},
                    ],
                }]

        result = services.import_from_splitwise(self.me, "fake-key", client=FakeClient())
        self.assertEqual(len(result["results"]), 1)
        r = result["results"][0]
        self.assertEqual(r["imported"], 1)
        g = Group.objects.get(id=r["group_id"])
        self.assertEqual(g.expenses.count(), 1)
        exp = g.expenses.first()
        self.assertEqual(exp.description, "SW Dinner")
        self.assertIsNotNone(exp.category)  # mapped to Food & Drink


@override_settings(FX_LIVE_FETCH=False)
class MultiCurrencyTests(BaseSetup):
    def test_usd_expense_converts_to_inr_base(self):
        DailyFxRate.objects.create(
            base="USD", quote="INR", rate=Decimal("80.0000000000"), as_of=TODAY, source="test"
        )
        exp = self._expense(
            description="US dinner", currency="USD", total_amount="10.00",
            payers=[{"member": self.m_me.id, "amount_paid": "10.00"}],
            splits=services.equal_split("10.00", [self.m_me.id, self.m_ritik.id]),
        )
        self.assertEqual(exp.base_amount, Decimal("800.00"))
        summary = balances_engine.group_summary(self.group)
        nets = {b["member_name"]: Decimal(b["net"]) for b in summary["balances"]}
        self.assertEqual(nets["Ritik"], Decimal("-400.00"))


class SimplifyTests(BaseSetup):
    def test_min_cash_flow_reduces_transactions(self):
        carol = Member.objects.create(group=self.group, display_name="Carol")
        # Me pays 90 split equally among 3 -> each owes 30.
        self._expense(
            total_amount="90.00",
            payers=[{"member": self.m_me.id, "amount_paid": "90.00"}],
            splits=services.equal_split("90.00", [self.m_me.id, self.m_ritik.id, carol.id]),
        )
        # Ritik pays 30 for Carol.
        self._expense(
            total_amount="30.00",
            payers=[{"member": self.m_ritik.id, "amount_paid": "30.00"}],
            splits=[{"member": carol.id, "share_amount": "30.00"}],
        )
        summary = balances_engine.group_summary(self.group)
        # Me is owed 60, Ritik net 0, Carol owes 60 -> single transaction.
        self.assertEqual(len(summary["suggested_settlements"]), 1)

    def test_settlement_clears_balance(self):
        self._expense(
            total_amount="100.00",
            payers=[{"member": self.m_me.id, "amount_paid": "100.00"}],
            splits=services.equal_split("100.00", [self.m_me.id, self.m_ritik.id]),
        )
        Settlement.objects.create(
            group=self.group, from_member=self.m_ritik, to_member=self.m_me,
            amount=Decimal("50.00"), currency="INR", date=TODAY,
        )
        summary = balances_engine.group_summary(self.group)
        self.assertEqual(summary["balances"], [])
        self.assertEqual(summary["suggested_settlements"], [])
