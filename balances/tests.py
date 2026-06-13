from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from groups.models import Group, GroupMembership
from expenses.models import Expense, ExpenseSplit
from .engine import (
    get_user_net_balance,
    get_group_balances,
    simplify_debts,
    get_balance_breakdown,
    _get_membership_date_ranges,
    _get_eligible_expense_ids,
    _get_settlement_net,
    _get_settlement_rows,
)

User = get_user_model()


class SettlementExtensionPointTests(TestCase):
    """
    Tests for the settlement extension point placeholder functions.

    Why: Validates that the settlement helpers return zero/empty results
    as documented, ensuring the balance engine operates correctly before
    the Settlement model is implemented.
    """

    def setUp(self):
        """
        Why: Creates minimal fixtures to pass required parameters.
        """
        self.user = User.objects.create_user(
            email="test@example.com", name="Test User", password="password123"
        )
        self.group = Group.objects.create(name="Test Group", created_by=self.user)

    def test_settlement_net_returns_zero(self):
        """
        Why: Extension point must return Decimal('0.00') until Settlement model exists.
        """
        result = _get_settlement_net(self.user, self.group, [])
        self.assertEqual(result, Decimal('0.00'))

    def test_settlement_rows_returns_empty_list(self):
        """
        Why: Extension point must return empty list until Settlement model exists.
        """
        result = _get_settlement_rows(self.user, self.group, [])
        self.assertEqual(result, [])


class NetBalanceCalculationTests(TestCase):
    """
    Unit tests for the net balance calculation engine.

    Why: Validates that credit (paid_by), debit (split.user), membership
    window filtering, and as_of_date filtering produce correct signed balances.
    """

    def setUp(self):
        """
        Why: Creates a group with 3 members and standard memberships
        for baseline balance scenarios.
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.member2 = User.objects.create_user(
            email="m2@example.com", name="Member 2", password="password123"
        )
        self.group = Group.objects.create(name="Balance Group", created_by=self.payer)

        # All 3 members active from Jan 1 onward
        GroupMembership.objects.create(
            group=self.group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.member1, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.member2, joined_at=date(2026, 1, 1)
        )

    def _create_expense_with_equal_splits(self, group, payer, amount, exp_date, members):
        """
        Why: Helper to create an ACTIVE expense with EQUAL splits among
        the specified members. Simulates the flow of ExpenseCreateView.
        """
        expense = Expense.objects.create(
            group=group,
            paid_by=payer,
            description=f"Expense {amount} on {exp_date}",
            date=exp_date,
            original_amount=amount,
            original_currency='INR',
            split_type='EQUAL',
            status='ACTIVE'
        )
        per_member = (amount / Decimal(len(members))).quantize(Decimal('0.01'))
        total_allocated = per_member * (len(members) - 1)
        payer_share = amount - total_allocated

        for m in members:
            share = payer_share if m == payer else per_member
            ExpenseSplit.objects.create(
                expense=expense, user=m, share_amount_inr=share
            )
            # Why: Assign payer remainder to first member who is payer
            if m == payer:
                payer_share = share  # Already set

        return expense

    def test_basic_equal_split_balances(self):
        """
        Why: Validates the fundamental credit - debit calculation.

        Scenario: Payer pays ₹300 split equally among 3 members.
        - Payer credit = 300, debit = 100 → net = +200 (owed ₹200)
        - Member1 credit = 0, debit = 100 → net = -100 (owes ₹100)
        - Member2 credit = 0, debit = 100 → net = -100 (owes ₹100)
        """
        members = [self.payer, self.member1, self.member2]
        expense = Expense.objects.create(
            group=self.group,
            paid_by=self.payer,
            description="Dinner",
            date=date(2026, 1, 15),
            original_amount=Decimal('300.00'),
            original_currency='INR',
            split_type='EQUAL',
            status='ACTIVE'
        )
        for m in members:
            ExpenseSplit.objects.create(
                expense=expense, user=m, share_amount_inr=Decimal('100.00')
            )

        self.assertEqual(
            get_user_net_balance(self.payer, self.group),
            Decimal('200.00')
        )
        self.assertEqual(
            get_user_net_balance(self.member1, self.group),
            Decimal('-100.00')
        )
        self.assertEqual(
            get_user_net_balance(self.member2, self.group),
            Decimal('-100.00')
        )

    def test_void_expenses_excluded(self):
        """
        Why: Validates that VOID and SUPERSEDED expenses are excluded
        from balance calculations. Only ACTIVE expenses count.
        """
        members = [self.payer, self.member1]

        # Active expense
        active_exp = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Active", date=date(2026, 1, 10),
            original_amount=Decimal('100.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=active_exp, user=self.payer, share_amount_inr=Decimal('50.00'))
        ExpenseSplit.objects.create(expense=active_exp, user=self.member1, share_amount_inr=Decimal('50.00'))

        # Void expense (should NOT count)
        void_exp = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Voided", date=date(2026, 1, 11),
            original_amount=Decimal('200.00'), original_currency='INR',
            split_type='EQUAL', status='VOID'
        )
        ExpenseSplit.objects.create(expense=void_exp, user=self.payer, share_amount_inr=Decimal('100.00'))
        ExpenseSplit.objects.create(expense=void_exp, user=self.member1, share_amount_inr=Decimal('100.00'))

        # Balance should only reflect the active expense
        self.assertEqual(
            get_user_net_balance(self.payer, self.group),
            Decimal('50.00')  # credit=100, debit=50 → +50
        )
        self.assertEqual(
            get_user_net_balance(self.member1, self.group),
            Decimal('-50.00')  # credit=0, debit=50 → -50
        )

    def test_no_membership_returns_zero(self):
        """
        Why: A user with no membership in the group should have zero balance.
        """
        outsider = User.objects.create_user(
            email="outsider@example.com", name="Outsider", password="password123"
        )
        self.assertEqual(
            get_user_net_balance(outsider, self.group),
            Decimal('0.00')
        )


class JoinedLateMemberTests(TestCase):
    """
    Tests for members who joined a group mid-month.

    Why: Validates that expenses incurred BEFORE a member's join date
    are excluded from their balance calculation, ensuring membership
    window filtering works correctly for late joiners.
    """

    def setUp(self):
        """
        Why: Creates a group where member2 joins on Jan 15, but expenses
        exist from Jan 5 (before join) and Jan 20 (after join).
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.late_joiner = User.objects.create_user(
            email="late@example.com", name="Late Joiner", password="password123"
        )
        self.group = Group.objects.create(name="Late Join Group", created_by=self.payer)

        # Payer and Member1 joined Jan 1
        GroupMembership.objects.create(
            group=self.group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.member1, joined_at=date(2026, 1, 1)
        )
        # Late Joiner joined Jan 15
        GroupMembership.objects.create(
            group=self.group, user=self.late_joiner, joined_at=date(2026, 1, 15)
        )

        # Expense on Jan 5 (before late_joiner) — split between payer and member1 only
        self.early_expense = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Early Dinner",
            date=date(2026, 1, 5),
            original_amount=Decimal('200.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(
            expense=self.early_expense, user=self.payer, share_amount_inr=Decimal('100.00')
        )
        ExpenseSplit.objects.create(
            expense=self.early_expense, user=self.member1, share_amount_inr=Decimal('100.00')
        )

        # Expense on Jan 20 (after late_joiner) — split among all 3
        self.late_expense = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Late Dinner",
            date=date(2026, 1, 20),
            original_amount=Decimal('300.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(
            expense=self.late_expense, user=self.payer, share_amount_inr=Decimal('100.00')
        )
        ExpenseSplit.objects.create(
            expense=self.late_expense, user=self.member1, share_amount_inr=Decimal('100.00')
        )
        ExpenseSplit.objects.create(
            expense=self.late_expense, user=self.late_joiner, share_amount_inr=Decimal('100.00')
        )

    def test_late_joiner_only_sees_expenses_after_join_date(self):
        """
        Why: Late joiner (joined Jan 15) should only see the Jan 20 expense.
        Their balance: credit=0 (didn't pay), debit=100 (split share) → -100.
        """
        balance = get_user_net_balance(self.late_joiner, self.group)
        self.assertEqual(balance, Decimal('-100.00'))

    def test_late_joiner_breakdown_excludes_early_expenses(self):
        """
        Why: Breakdown for late joiner should only contain rows for
        the Jan 20 expense, not the Jan 5 expense.
        """
        breakdown = get_balance_breakdown(self.late_joiner, self.group)
        # Only 1 debit row for the Jan 20 expense
        self.assertEqual(len(breakdown), 1)
        self.assertEqual(breakdown[0]['type'], 'expense_debit')
        self.assertEqual(breakdown[0]['date'], date(2026, 1, 20))

    def test_payer_sees_both_expenses(self):
        """
        Why: Payer (joined Jan 1) should see both expenses.
        Credit: 200 (early) + 300 (late) = 500
        Debit: 100 (early) + 100 (late) = 200
        Net: +300
        """
        balance = get_user_net_balance(self.payer, self.group)
        self.assertEqual(balance, Decimal('300.00'))


class LeftMemberTests(TestCase):
    """
    Tests for members who left a group.

    Why: Validates that expenses incurred AFTER a member's leave date
    are excluded from their balance calculation.
    """

    def setUp(self):
        """
        Why: Creates a group where member1 leaves on Jan 10,
        with expenses on Jan 5 (before leave) and Jan 20 (after leave).
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.leaver = User.objects.create_user(
            email="leaver@example.com", name="Leaver", password="password123"
        )
        self.stayer = User.objects.create_user(
            email="stayer@example.com", name="Stayer", password="password123"
        )
        self.group = Group.objects.create(name="Leave Group", created_by=self.payer)

        # All joined Jan 1
        GroupMembership.objects.create(
            group=self.group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.stayer, joined_at=date(2026, 1, 1)
        )
        # Leaver left on Jan 10
        GroupMembership.objects.create(
            group=self.group, user=self.leaver,
            joined_at=date(2026, 1, 1), left_at=date(2026, 1, 10)
        )

        # Expense on Jan 5 (before leave) — all 3 members
        self.before_leave_expense = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Before Leave",
            date=date(2026, 1, 5),
            original_amount=Decimal('300.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        for m in [self.payer, self.leaver, self.stayer]:
            ExpenseSplit.objects.create(
                expense=self.before_leave_expense, user=m,
                share_amount_inr=Decimal('100.00')
            )

        # Expense on Jan 20 (after leave) — only payer and stayer
        self.after_leave_expense = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="After Leave",
            date=date(2026, 1, 20),
            original_amount=Decimal('200.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        for m in [self.payer, self.stayer]:
            ExpenseSplit.objects.create(
                expense=self.after_leave_expense, user=m,
                share_amount_inr=Decimal('100.00')
            )

    def test_leaver_only_sees_expenses_before_leave_date(self):
        """
        Why: Leaver (left Jan 10) should only see the Jan 5 expense.
        Balance: credit=0, debit=100 → -100.
        """
        balance = get_user_net_balance(self.leaver, self.group)
        self.assertEqual(balance, Decimal('-100.00'))

    def test_leaver_does_not_see_expenses_after_leave_date(self):
        """
        Why: Breakdown for leaver should only contain the Jan 5 expense row.
        """
        breakdown = get_balance_breakdown(self.leaver, self.group)
        self.assertEqual(len(breakdown), 1)
        self.assertEqual(breakdown[0]['date'], date(2026, 1, 5))

    def test_payer_sees_both_expenses(self):
        """
        Why: Payer (still active) sees both.
        Credit: 300 + 200 = 500
        Debit: 100 + 100 = 200
        Net: +300
        """
        balance = get_user_net_balance(self.payer, self.group)
        self.assertEqual(balance, Decimal('300.00'))


class AsOfDateFilteringTests(TestCase):
    """
    Tests for as_of_date filtering in net balance calculations.

    Why: Validates that the as_of_date parameter correctly excludes
    expenses that occurred after the specified date.
    """

    def setUp(self):
        """
        Why: Creates expenses on Jan 10 and Jan 20, so we can verify
        filtering at Jan 15 excludes the later expense.
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.group = Group.objects.create(name="Date Filter Group", created_by=self.payer)

        GroupMembership.objects.create(
            group=self.group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.member1, joined_at=date(2026, 1, 1)
        )

        # Expense on Jan 10
        exp1 = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Jan 10 expense",
            date=date(2026, 1, 10),
            original_amount=Decimal('100.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=exp1, user=self.payer, share_amount_inr=Decimal('50.00'))
        ExpenseSplit.objects.create(expense=exp1, user=self.member1, share_amount_inr=Decimal('50.00'))

        # Expense on Jan 20
        exp2 = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Jan 20 expense",
            date=date(2026, 1, 20),
            original_amount=Decimal('200.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=exp2, user=self.payer, share_amount_inr=Decimal('100.00'))
        ExpenseSplit.objects.create(expense=exp2, user=self.member1, share_amount_inr=Decimal('100.00'))

    def test_as_of_date_includes_only_expenses_on_or_before(self):
        """
        Why: as_of_date=Jan 15 should only include the Jan 10 expense.
        Payer: credit=100, debit=50 → +50
        """
        balance = get_user_net_balance(
            self.payer, self.group, as_of_date=date(2026, 1, 15)
        )
        self.assertEqual(balance, Decimal('50.00'))

    def test_as_of_date_none_includes_all(self):
        """
        Why: as_of_date=None should include both expenses.
        Payer: credit=300, debit=150 → +150
        """
        balance = get_user_net_balance(self.payer, self.group, as_of_date=None)
        self.assertEqual(balance, Decimal('150.00'))

    def test_as_of_date_exact_boundary(self):
        """
        Why: as_of_date=Jan 10 should include the Jan 10 expense (inclusive).
        """
        balance = get_user_net_balance(
            self.payer, self.group, as_of_date=date(2026, 1, 10)
        )
        self.assertEqual(balance, Decimal('50.00'))

    def test_as_of_date_before_all_expenses(self):
        """
        Why: as_of_date=Jan 1 (before any expenses) should return zero.
        """
        balance = get_user_net_balance(
            self.payer, self.group, as_of_date=date(2026, 1, 1)
        )
        self.assertEqual(balance, Decimal('0.00'))


class MultipleGroupsTests(TestCase):
    """
    Tests for balance isolation across multiple groups.

    Why: Validates that expenses in one group do not leak into
    balance calculations for another group.
    """

    def setUp(self):
        """
        Why: Creates two separate groups with the same users but
        different expenses, to prove cross-group isolation.
        """
        self.user_a = User.objects.create_user(
            email="a@example.com", name="User A", password="password123"
        )
        self.user_b = User.objects.create_user(
            email="b@example.com", name="User B", password="password123"
        )

        self.group1 = Group.objects.create(name="Group 1", created_by=self.user_a)
        self.group2 = Group.objects.create(name="Group 2", created_by=self.user_a)

        # Both users in both groups
        for g in [self.group1, self.group2]:
            GroupMembership.objects.create(group=g, user=self.user_a, joined_at=date(2026, 1, 1))
            GroupMembership.objects.create(group=g, user=self.user_b, joined_at=date(2026, 1, 1))

        # Group 1: A pays ₹100
        exp1 = Expense.objects.create(
            group=self.group1, paid_by=self.user_a,
            description="G1 expense",
            date=date(2026, 1, 10),
            original_amount=Decimal('100.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=exp1, user=self.user_a, share_amount_inr=Decimal('50.00'))
        ExpenseSplit.objects.create(expense=exp1, user=self.user_b, share_amount_inr=Decimal('50.00'))

        # Group 2: B pays ₹400
        exp2 = Expense.objects.create(
            group=self.group2, paid_by=self.user_b,
            description="G2 expense",
            date=date(2026, 1, 10),
            original_amount=Decimal('400.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=exp2, user=self.user_a, share_amount_inr=Decimal('200.00'))
        ExpenseSplit.objects.create(expense=exp2, user=self.user_b, share_amount_inr=Decimal('200.00'))

    def test_group1_balances_isolated(self):
        """
        Why: Group 1 balances should only reflect the ₹100 expense.
        A: credit=100, debit=50 → +50
        B: credit=0, debit=50 → -50
        """
        self.assertEqual(
            get_user_net_balance(self.user_a, self.group1), Decimal('50.00')
        )
        self.assertEqual(
            get_user_net_balance(self.user_b, self.group1), Decimal('-50.00')
        )

    def test_group2_balances_isolated(self):
        """
        Why: Group 2 balances should only reflect the ₹400 expense.
        A: credit=0, debit=200 → -200
        B: credit=400, debit=200 → +200
        """
        self.assertEqual(
            get_user_net_balance(self.user_a, self.group2), Decimal('-200.00')
        )
        self.assertEqual(
            get_user_net_balance(self.user_b, self.group2), Decimal('200.00')
        )


class GroupBalancesTests(TestCase):
    """
    Tests for the get_group_balances() aggregation function.

    Why: Validates that get_group_balances returns correct per-member
    balances and includes historical (left) members.
    """

    def setUp(self):
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.group = Group.objects.create(name="Group Bal", created_by=self.payer)
        GroupMembership.objects.create(
            group=self.group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.member1, joined_at=date(2026, 1, 1)
        )

        exp = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Dinner",
            date=date(2026, 1, 10),
            original_amount=Decimal('100.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=exp, user=self.payer, share_amount_inr=Decimal('50.00'))
        ExpenseSplit.objects.create(expense=exp, user=self.member1, share_amount_inr=Decimal('50.00'))

    def test_returns_all_members(self):
        """
        Why: get_group_balances should return a balance for every member.
        """
        balances = get_group_balances(self.group)
        user_ids = {u.id for u in balances.keys()}
        self.assertIn(self.payer.id, user_ids)
        self.assertIn(self.member1.id, user_ids)

    def test_balances_sum_to_zero(self):
        """
        Why: In a group where all members have identical membership windows,
        the sum of all balances must be exactly zero (conservation of money).
        """
        balances = get_group_balances(self.group)
        total = sum(balances.values())
        self.assertEqual(total, Decimal('0.00'))


class SimplifyDebtsTests(TestCase):
    """
    Tests for the greedy debt simplification algorithm.

    Why: Validates the 5 invariants:
    1. Total balances preserved exactly
    2. Never creates money
    3. Never destroys money
    4. Output transaction sum equals total positive balances
    5. sum(credits) == sum(debits) across all transactions
    """

    def setUp(self):
        """
        Why: Creates a 4-member group with multiple expenses paid by
        different members, creating a complex debt web.

        Scenario:
        - Payer pays ₹400 split equally (4 × ₹100)
        - Member1 pays ₹200 split equally (4 × ₹50)
        - Member2 and Member3 pay nothing

        Expected net balances:
        - Payer: credit=400, debit=150 → +250
        - Member1: credit=200, debit=150 → +50
        - Member2: credit=0, debit=150 → -150
        - Member3: credit=0, debit=150 → -150
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.member2 = User.objects.create_user(
            email="m2@example.com", name="Member 2", password="password123"
        )
        self.member3 = User.objects.create_user(
            email="m3@example.com", name="Member 3", password="password123"
        )
        self.group = Group.objects.create(name="Simplify Group", created_by=self.payer)

        members = [self.payer, self.member1, self.member2, self.member3]
        for m in members:
            GroupMembership.objects.create(
                group=self.group, user=m, joined_at=date(2026, 1, 1)
            )

        # Payer pays ₹400
        exp1 = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Big Dinner", date=date(2026, 1, 10),
            original_amount=Decimal('400.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        for m in members:
            ExpenseSplit.objects.create(
                expense=exp1, user=m, share_amount_inr=Decimal('100.00')
            )

        # Member1 pays ₹200
        exp2 = Expense.objects.create(
            group=self.group, paid_by=self.member1,
            description="Groceries", date=date(2026, 1, 15),
            original_amount=Decimal('200.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        for m in members:
            ExpenseSplit.objects.create(
                expense=exp2, user=m, share_amount_inr=Decimal('50.00')
            )

    def test_sum_credits_equals_sum_debits(self):
        """
        Why: The total amount flowing through all simplified transactions
        must equal the total positive balances (and the absolute total of
        negative balances). This proves money is conserved.
        """
        transactions = simplify_debts(self.group)
        balances = get_group_balances(self.group)

        total_positive = sum(b for b in balances.values() if b > 0)
        total_negative = sum(b for b in balances.values() if b < 0)
        transaction_total = sum(t[2] for t in transactions)

        # Sum of positive balances equals sum of transaction amounts
        self.assertEqual(transaction_total, total_positive)
        # Sum of positive balances equals absolute value of negative balances
        self.assertEqual(total_positive, abs(total_negative))

    def test_no_money_created(self):
        """
        Why: No individual transaction should exceed the original balance
        of either the payer or the payee.
        """
        transactions = simplify_debts(self.group)
        balances = get_group_balances(self.group)

        for from_user, to_user, amount in transactions:
            # Amount should not exceed what the debtor owes
            self.assertLessEqual(amount, abs(balances[from_user]))
            # Amount should not exceed what the creditor is owed
            self.assertLessEqual(amount, balances[to_user])

    def test_no_money_destroyed(self):
        """
        Why: After applying all simplified transactions, every member's
        effective net position should be zero.
        """
        transactions = simplify_debts(self.group)
        balances = get_group_balances(self.group)

        # Simulate applying transactions
        effective = {u: b for u, b in balances.items()}
        for from_user, to_user, amount in transactions:
            effective[from_user] += amount  # Debtor pays (negative balance moves toward 0)
            effective[to_user] -= amount    # Creditor receives (positive balance moves toward 0)

        for user, remaining in effective.items():
            self.assertEqual(
                remaining, Decimal('0.00'),
                f"{user.name} has remaining balance {remaining} after all transactions"
            )

    def test_transactions_have_positive_amounts(self):
        """
        Why: Every transaction amount must be strictly positive.
        Zero or negative amounts would indicate an algorithmic error.
        """
        transactions = simplify_debts(self.group)
        for from_user, to_user, amount in transactions:
            self.assertGreater(amount, Decimal('0.00'))

    def test_from_and_to_users_differ(self):
        """
        Why: A user should never pay themselves in simplified debts.
        """
        transactions = simplify_debts(self.group)
        for from_user, to_user, amount in transactions:
            self.assertNotEqual(from_user, to_user)

    def test_all_settled_returns_empty(self):
        """
        Why: If all balances are zero, simplify_debts should return
        an empty transaction list.
        """
        # Create a group with no expenses
        settled_group = Group.objects.create(name="Settled", created_by=self.payer)
        GroupMembership.objects.create(
            group=settled_group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        transactions = simplify_debts(settled_group)
        self.assertEqual(transactions, [])


class SettlementsIntegrationTests(TestCase):
    """
    Tests for the settlement extension point behavior within
    balance calculations.

    Why: Validates that balances are correctly computed as expense-only
    when the Settlement model does not exist. When settlements are
    implemented, these tests should be updated to include settlement data.
    """

    def setUp(self):
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.group = Group.objects.create(name="Settlement Group", created_by=self.payer)
        GroupMembership.objects.create(
            group=self.group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.member1, joined_at=date(2026, 1, 1)
        )

        exp = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Test Expense", date=date(2026, 1, 10),
            original_amount=Decimal('100.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=exp, user=self.payer, share_amount_inr=Decimal('50.00'))
        ExpenseSplit.objects.create(expense=exp, user=self.member1, share_amount_inr=Decimal('50.00'))

    def test_balance_is_expense_only_without_settlements(self):
        """
        Why: With no Settlement model, balance should reflect only expenses.
        Settlement extension point contributes Decimal('0.00').
        """
        # Payer: credit=100, debit=50, settlement=0 → +50
        self.assertEqual(
            get_user_net_balance(self.payer, self.group), Decimal('50.00')
        )
        # Member1: credit=0, debit=50, settlement=0 → -50
        self.assertEqual(
            get_user_net_balance(self.member1, self.group), Decimal('-50.00')
        )

    def test_breakdown_has_no_settlement_rows(self):
        """
        Why: With no Settlement model, breakdown should only contain
        expense credit and debit rows, no settlement rows.
        """
        breakdown = get_balance_breakdown(self.payer, self.group)
        settlement_rows = [r for r in breakdown if 'settlement' in r['type']]
        self.assertEqual(len(settlement_rows), 0)


class BalanceBreakdownTests(TestCase):
    """
    Tests for the get_balance_breakdown() traceable audit function.

    Why: Validates that every row in the breakdown maps to a real
    database record, amounts are correctly signed, and the sum
    of all rows equals the net balance.
    """

    def setUp(self):
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.group = Group.objects.create(name="Breakdown Group", created_by=self.payer)
        GroupMembership.objects.create(
            group=self.group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.member1, joined_at=date(2026, 1, 1)
        )

        # Two expenses
        self.exp1 = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="Expense 1", date=date(2026, 1, 5),
            original_amount=Decimal('100.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=self.exp1, user=self.payer, share_amount_inr=Decimal('50.00'))
        ExpenseSplit.objects.create(expense=self.exp1, user=self.member1, share_amount_inr=Decimal('50.00'))

        self.exp2 = Expense.objects.create(
            group=self.group, paid_by=self.member1,
            description="Expense 2", date=date(2026, 1, 10),
            original_amount=Decimal('60.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=self.exp2, user=self.payer, share_amount_inr=Decimal('30.00'))
        ExpenseSplit.objects.create(expense=self.exp2, user=self.member1, share_amount_inr=Decimal('30.00'))

    def test_breakdown_sum_equals_net_balance(self):
        """
        Why: The sum of all signed amounts in the breakdown must
        equal the net balance from get_user_net_balance.
        """
        breakdown = get_balance_breakdown(self.payer, self.group)
        breakdown_sum = sum(row['amount'] for row in breakdown)
        net_balance = get_user_net_balance(self.payer, self.group)
        self.assertEqual(breakdown_sum, net_balance)

    def test_every_row_has_record_id(self):
        """
        Why: Every breakdown row must have a record_id and record_model
        for traceability back to the source database record.
        """
        breakdown = get_balance_breakdown(self.payer, self.group)
        for row in breakdown:
            self.assertIn('record_id', row)
            self.assertIn('record_model', row)
            self.assertIsNotNone(row['record_id'])
            self.assertIsNotNone(row['record_model'])

    def test_credit_rows_are_positive_debit_rows_are_negative(self):
        """
        Why: Credit rows (user paid) must have positive amounts,
        debit rows (user owes) must have negative amounts.
        """
        breakdown = get_balance_breakdown(self.payer, self.group)
        for row in breakdown:
            if row['type'] == 'expense_credit':
                self.assertGreater(row['amount'], Decimal('0.00'))
            elif row['type'] == 'expense_debit':
                self.assertLess(row['amount'], Decimal('0.00'))

    def test_payer_breakdown_has_credits_and_debits(self):
        """
        Why: Payer paid for exp1 (credit) and has splits in both exp1 and exp2 (debits).
        Expected rows:
        - 1 credit row for exp1 (paid ₹100)
        - 1 debit row for exp1 share (-₹50)
        - 1 debit row for exp2 share (-₹30)
        Total: 100 - 50 - 30 = +20
        """
        breakdown = get_balance_breakdown(self.payer, self.group)
        credits = [r for r in breakdown if r['type'] == 'expense_credit']
        debits = [r for r in breakdown if r['type'] == 'expense_debit']

        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0]['amount'], Decimal('100.00'))

        self.assertEqual(len(debits), 2)
        debit_amounts = sorted([r['amount'] for r in debits])
        self.assertEqual(debit_amounts, [Decimal('-50.00'), Decimal('-30.00')])

    def test_rows_sorted_by_date(self):
        """
        Why: Breakdown rows must be sorted by date ascending for
        chronological readability.
        """
        breakdown = get_balance_breakdown(self.payer, self.group)
        dates = [row['date'] for row in breakdown]
        self.assertEqual(dates, sorted(dates))


class BalanceViewsTests(TestCase):
    """
    Integration tests for balance template views.

    Why: Validates that the 3 balance views render correctly,
    require authentication, and pass correct context data.
    """

    def setUp(self):
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.group = Group.objects.create(name="View Group", created_by=self.payer)
        GroupMembership.objects.create(
            group=self.group, user=self.payer, joined_at=date(2026, 1, 1)
        )
        GroupMembership.objects.create(
            group=self.group, user=self.member1, joined_at=date(2026, 1, 1)
        )

        exp = Expense.objects.create(
            group=self.group, paid_by=self.payer,
            description="View Test Expense", date=date(2026, 1, 10),
            original_amount=Decimal('100.00'), original_currency='INR',
            split_type='EQUAL', status='ACTIVE'
        )
        ExpenseSplit.objects.create(expense=exp, user=self.payer, share_amount_inr=Decimal('50.00'))
        ExpenseSplit.objects.create(expense=exp, user=self.member1, share_amount_inr=Decimal('50.00'))

        self.client.login(username=self.payer.email, password="password123")

    def test_group_balance_summary_view(self):
        """
        Why: Validates the group balance summary page renders and
        contains member names and balance data.
        """
        url = reverse('group_balance_summary', args=[self.group.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payer")
        self.assertContains(response, "Member 1")
        self.assertIn('balances', response.context)

    def test_balance_detail_view(self):
        """
        Why: Validates the balance detail page renders breakdown
        rows for a specific user.
        """
        url = reverse('balance_detail', kwargs={
            'group_pk': self.group.pk,
            'user_pk': self.payer.pk
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payer")
        self.assertIn('breakdown', response.context)
        self.assertIn('net_total', response.context)

    def test_simplified_debts_view(self):
        """
        Why: Validates the simplified debts page renders transactions.
        """
        url = reverse('simplified_debts', args=[self.group.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('transactions', response.context)

    def test_views_require_authentication(self):
        """
        Why: All balance views must redirect unauthenticated users to login.
        """
        self.client.logout()
        urls = [
            reverse('group_balance_summary', args=[self.group.pk]),
            reverse('balance_detail', kwargs={
                'group_pk': self.group.pk, 'user_pk': self.payer.pk
            }),
            reverse('simplified_debts', args=[self.group.pk]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(
                response.status_code, 302,
                f"Expected redirect for unauthenticated access to {url}"
            )
