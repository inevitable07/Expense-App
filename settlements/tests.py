from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import ValidationError

from groups.models import Group, GroupMembership
from expenses.models import Expense, ExpenseSplit
from settlements.models import Settlement
from balances.engine import get_user_net_balance, get_balance_breakdown, get_group_balances

User = get_user_model()


class SettlementModelTests(TestCase):
    """
    Tests for the Settlement model validation rules and behavior.

    Why: Ensures data integrity at the database layer, specifically verifying
    positive amount rules and self-payment prevention constraints.
    """

    def setUp(self):
        """
        Why: Creates standard user and group fixtures for testing.
        """
        self.user_a = User.objects.create_user(
            email="usera@example.com", name="User A", password="password123"
        )
        self.user_b = User.objects.create_user(
            email="userb@example.com", name="User B", password="password123"
        )
        self.group = Group.objects.create(name="Settlement Test Group", created_by=self.user_a)

    def test_amount_must_be_positive(self):
        """
        Why: Enforces that zero or negative settlement amounts are rejected.
        """
        settlement = Settlement(
            group=self.group,
            paid_by=self.user_a,
            paid_to=self.user_b,
            amount_inr=Decimal('-10.00'),
            date=date(2026, 6, 1)
        )
        with self.assertRaises(ValidationError):
            settlement.save()

        settlement.amount_inr = Decimal('0.00')
        with self.assertRaises(ValidationError):
            settlement.save()

        # Positive amount should save successfully
        settlement.amount_inr = Decimal('100.00')
        settlement.save()
        self.assertIsNotNone(settlement.pk)

    def test_prevent_self_payment(self):
        """
        Why: Enforces that a member cannot record a settlement payment to themselves.
        """
        settlement = Settlement(
            group=self.group,
            paid_by=self.user_a,
            paid_to=self.user_a,
            amount_inr=Decimal('50.00'),
            date=date(2026, 6, 1)
        )
        with self.assertRaises(ValidationError):
            settlement.save()


class SettlementIntegrationAndEngineTests(TestCase):
    """
    Tests the integration of settlements into the balances engine.

    Why: Validates the core balance-scoping requirements:
    1. Settlement reduces outstanding debt.
    2. Settlement clears balance entirely (moves to zero).
    3. Settlement history traceability (appears correctly in breakdown).
    4. Settlements are never treated as expenses.
    """

    def setUp(self):
        """
        Why: Sets up a group with two active members.
        """
        self.debtor = User.objects.create_user(
            email="debtor@example.com", name="Debtor Member", password="password123"
        )
        self.creditor = User.objects.create_user(
            email="creditor@example.com", name="Creditor Member", password="password123"
        )
        self.group = Group.objects.create(name="Shared Trip", created_by=self.creditor)

        GroupMembership.objects.create(group=self.group, user=self.debtor, joined_at=date(2026, 6, 1))
        GroupMembership.objects.create(group=self.group, user=self.creditor, joined_at=date(2026, 6, 1))

    def _record_expense_imbalance(self, amount):
        """
        Why: Helper to create a split expense where Creditor pays and both split equally.
        This leaves the Debtor owing half of the amount.
        """
        expense = Expense.objects.create(
            group=self.group,
            paid_by=self.creditor,
            description="Shared Cab",
            date=date(2026, 6, 5),
            original_amount=amount,
            original_currency='INR',
            split_type='EQUAL',
            status='ACTIVE'
        )
        share = amount / Decimal('2.00')
        ExpenseSplit.objects.create(expense=expense, user=self.creditor, share_amount_inr=share)
        ExpenseSplit.objects.create(expense=expense, user=self.debtor, share_amount_inr=share)
        return expense

    def test_settlement_reduces_debt(self):
        """
        Why: Verifies that recording a partial settlement decreases outstanding net debt.
        """
        # Creditor pays ₹200. Debtor owes ₹100.
        self._record_expense_imbalance(Decimal('200.00'))

        self.assertEqual(get_user_net_balance(self.debtor, self.group), Decimal('-100.00'))
        self.assertEqual(get_user_net_balance(self.creditor, self.group), Decimal('100.00'))

        # Debtor pays ₹40 settlement
        Settlement.objects.create(
            group=self.group,
            paid_by=self.debtor,
            paid_to=self.creditor,
            amount_inr=Decimal('40.00'),
            date=date(2026, 6, 10)
        )

        # Net balance should adjust to -60 and +60 respectively
        self.assertEqual(get_user_net_balance(self.debtor, self.group), Decimal('-60.00'))
        self.assertEqual(get_user_net_balance(self.creditor, self.group), Decimal('60.00'))

    def test_settlement_clears_balance(self):
        """
        Why: Proves that recording a payment matching the exact balance clears the net position to zero.
        """
        # Creditor pays ₹300. Debtor owes ₹150.
        self._record_expense_imbalance(Decimal('300.00'))

        # Record settlement clearing the entire ₹150 debt
        Settlement.objects.create(
            group=self.group,
            paid_by=self.debtor,
            paid_to=self.creditor,
            amount_inr=Decimal('150.00'),
            date=date(2026, 6, 10)
        )

        # Confirm balances are fully settled to zero
        self.assertEqual(get_user_net_balance(self.debtor, self.group), Decimal('0.00'))
        self.assertEqual(get_user_net_balance(self.creditor, self.group), Decimal('0.00'))

    def test_settlement_never_treated_as_expense(self):
        """
        Why: Confirms that Settlements are separately managed and never fetched in Expense querysets.
        """
        self._record_expense_imbalance(Decimal('100.00'))
        
        # Record settlement
        Settlement.objects.create(
            group=self.group,
            paid_by=self.debtor,
            paid_to=self.creditor,
            amount_inr=Decimal('50.00'),
            date=date(2026, 6, 10)
        )

        # Expense count should remain exactly 1, and Settlement count is 1
        self.assertEqual(Expense.objects.filter(group=self.group).count(), 1)
        self.assertEqual(Settlement.objects.filter(group=self.group).count(), 1)

    def test_settlement_history_traceability(self):
        """
        Why: Validates that settlements are listed separately in the balance breakdown
        drill-down view to support audit logging.
        """
        self._record_expense_imbalance(Decimal('100.00'))
        
        settlement = Settlement.objects.create(
            group=self.group,
            paid_by=self.debtor,
            paid_to=self.creditor,
            amount_inr=Decimal('50.00'),
            date=date(2026, 6, 10),
            note="Paid via UPI"
        )

        # Check debtor's breakdown
        breakdown = get_balance_breakdown(self.debtor, self.group)
        
        # Debtor should have: 1 expense split debit (-50) and 1 settlement credit (+50)
        self.assertEqual(len(breakdown), 2)
        
        # Verify settlement row fields
        settlement_row = [r for r in breakdown if r['record_model'] == 'Settlement'][0]
        self.assertEqual(settlement_row['type'], 'settlement_credit')
        self.assertEqual(settlement_row['amount'], Decimal('50.00'))
        self.assertEqual(settlement_row['record_id'], settlement.id)
        self.assertEqual(settlement_row['date'], date(2026, 6, 10))


class SettlementViewsTests(TestCase):
    """
    Tests for settlements templates rendering views.

    Why: Validates that views display records, authenticate users,
    and process dynamic dropdown lists.
    """

    def setUp(self):
        """
        Why: Setup sample groups and log in the user client.
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member = User.objects.create_user(
            email="member@example.com", name="Member", password="password123"
        )
        self.group = Group.objects.create(name="Trip Group", created_by=self.payer)

        GroupMembership.objects.create(group=self.group, user=self.payer, joined_at=date(2026, 6, 1))
        GroupMembership.objects.create(group=self.group, user=self.member, joined_at=date(2026, 6, 1))

        self.client.login(username=self.payer.email, password="password123")

    def test_create_settlement_view_get(self):
        """
        Why: Confirms form displays with preselected group when requested.
        """
        url = f"{reverse('settlement_create')}?group={self.group.pk}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Record a Payment")
        self.assertIn('group_members_json', response.context)

    def test_create_settlement_view_post(self):
        """
        Why: Confirms posting valid form input saves settlement to DB and redirects.
        """
        url = reverse('settlement_create')
        data = {
            'group': self.group.pk,
            'paid_by': self.payer.pk,
            'paid_to': self.member.pk,
            'amount_inr': '45.50',
            'date': '2026-06-12',
            'note': 'Cash payment'
        }
        response = self.client.post(url, data)
        # Should redirect to chronological settlement list page
        self.assertEqual(response.status_code, 302)
        
        # Verify db persistence
        self.assertEqual(Settlement.objects.count(), 1)
        s = Settlement.objects.first()
        self.assertEqual(s.amount_inr, Decimal('45.50'))
        self.assertEqual(s.note, 'Cash payment')

    def test_settlements_list_view(self):
        """
        Why: Confirms chronological view lists settlement payments correctly.
        """
        s1 = Settlement.objects.create(
            group=self.group, paid_by=self.payer, paid_to=self.member,
            amount_inr=Decimal('10.00'), date=date(2026, 6, 12), note="UPI Ref 1"
        )
        s2 = Settlement.objects.create(
            group=self.group, paid_by=self.payer, paid_to=self.member,
            amount_inr=Decimal('20.00'), date=date(2026, 6, 13), note="UPI Ref 2"
        )

        url = reverse('settlement_list', kwargs={'group_id': self.group.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "UPI Ref 1")
        self.assertContains(response, "UPI Ref 2")
