from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models import FXRate
from groups.models import Group
from .models import Expense, ExpenseSplit
from .services import compute_splits

User = get_user_model()

class ExpenseModelAndFXTests(TestCase):
    """
    Unit tests for Expense model validation, currency conversion, and rounding.
    
    Why: Validates that foreign currency conversions are computed using active rates
    and rounded only at the database save boundary.
    """

    def setUp(self):
        """
        Why: Sets up baseline user, group, and exchange rates.
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer User", password="password123"
        )
        self.group = Group.objects.create(name="Travelers", created_by=self.payer)
        self.fx_rate = FXRate.objects.create(
            from_currency="USD",
            to_currency="INR",
            rate=Decimal("83.456789"),  # Test with high precision rate
            effective_date=date(2026, 6, 1)
        )

    def test_inr_expense_does_not_require_fx_rate(self):
        """
        Why: Assures that standard INR expenses bypass FX validations and set amount_inr directly.
        """
        expense = Expense(
            group=self.group,
            paid_by=self.payer,
            description="Lunch in Delhi",
            date=date(2026, 6, 1),
            original_amount=Decimal("1500.00"),
            original_currency="INR",
            split_type="EQUAL"
        )
        try:
            expense.save()
            self.assertEqual(expense.amount_inr, Decimal("1500.00"))
        except ValidationError:
            self.fail("ValidationError raised unexpectedly for INR transaction without FX Rate.")

    def test_usd_expense_requires_fx_rate(self):
        """
        Why: Assures that saving a USD transaction without providing an FXRate raises a validation error.
        """
        expense = Expense(
            group=self.group,
            paid_by=self.payer,
            description="Taxi in New York",
            date=date(2026, 6, 1),
            original_amount=Decimal("50.00"),
            original_currency="USD",
            split_type="EQUAL"
        )
        with self.assertRaises(ValidationError):
            expense.save()

    def test_usd_expense_calculates_and_rounds_inr(self):
        """
        Why: Verifies currency conversion: USD original amount converted using rate
        and rounded to 2 decimal places using ROUND_HALF_UP.
        
        Calculation: 50.00 * 83.456789 = 4172.83945 => rounded to 4172.84 INR.
        """
        expense = Expense(
            group=self.group,
            paid_by=self.payer,
            description="Dinner in Boston",
            date=date(2026, 6, 1),
            original_amount=Decimal("50.00"),
            original_currency="USD",
            fx_rate_used=self.fx_rate,
            split_type="EQUAL"
        )
        expense.save()
        self.assertEqual(expense.amount_inr, Decimal("4172.84"))


class SplitEngineTests(TestCase):
    """
    Unit tests for the split calculation engine strategies.
    
    Why: Validates mathematical splits correctness, percentage boundaries,
    and allocation of remainder cents to the payer.
    """

    def setUp(self):
        """
        Why: Sets up baseline members and an expense instance.
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer User", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.member2 = User.objects.create_user(
            email="m2@example.com", name="Member 2", password="password123"
        )
        
        self.group = Group.objects.create(name="Flatmates", created_by=self.payer)
        self.members = [self.payer, self.member1, self.member2]
        
        # Base INR expense for ₹100.00
        self.expense_100 = Expense(
            group=self.group,
            paid_by=self.payer,
            description="Shared Grocery",
            date=date(2026, 6, 1),
            original_amount=Decimal("100.00"),
            original_currency="INR",
            split_type="EQUAL"
        )
        self.expense_100.save()

    def test_equal_split_rounding_policy_100_3_ways(self):
        """
        Why: Verifies the required ₹100 split 3 ways scenario.
        Expected:
        - Base share: floor(100 / 3) = 33.33
        - Payer receives remainder cents: 100 - (33.33 * 3) = 0.01
        - Payer share: 33.33 + 0.01 = 33.34
        - Others share: 33.33
        """
        splits = compute_splits(self.expense_100, split_input=None, members=self.members)
        
        self.assertEqual(splits[self.payer.id], Decimal("33.34"))
        self.assertEqual(splits[self.member1.id], Decimal("33.33"))
        self.assertEqual(splits[self.member2.id], Decimal("33.33"))
        self.assertEqual(sum(splits.values()), Decimal("100.00"))

    def test_exact_split_sum_validation(self):
        """
        Why: Verifies EXACT splits sum validation. Must match total amount_inr exactly.
        """
        self.expense_100.split_type = "EXACT"
        self.expense_100.save()
        
        # Valid input sum = 100.00
        valid_input = {
            self.payer.id: Decimal("50.00"),
            self.member1.id: Decimal("30.00"),
            self.member2.id: Decimal("20.00")
        }
        splits = compute_splits(self.expense_100, valid_input, self.members)
        self.assertEqual(sum(splits.values()), Decimal("100.00"))

        # Invalid input sum = 95.00 (fails)
        invalid_input = {
            self.payer.id: Decimal("50.00"),
            self.member1.id: Decimal("25.00"),
            self.member2.id: Decimal("20.00")
        }
        with self.assertRaises(ValidationError):
            compute_splits(self.expense_100, invalid_input, self.members)

    def test_percentage_split_edge_cases(self):
        """
        Why: Verifies PERCENTAGE splits sum to 100%, and rounding allocations.
        
        Test Case: ₹100 split with 33.33%, 33.33%, 33.34%.
        Payer gets 33.33% => 33.33.
        Member 1 gets 33.33% => 33.33.
        Member 2 gets 33.34% => 33.34.
        Sum is exactly 100.00. No remainder.
        """
        self.expense_100.split_type = "PERCENTAGE"
        self.expense_100.save()
        
        # Sum of % is 100
        pct_input = {
            self.payer.id: Decimal("33.33"),
            self.member1.id: Decimal("33.33"),
            self.member2.id: Decimal("33.34")
        }
        splits = compute_splits(self.expense_100, pct_input, self.members)
        self.assertEqual(splits[self.payer.id], Decimal("33.33"))
        self.assertEqual(splits[self.member1.id], Decimal("33.33"))
        self.assertEqual(splits[self.member2.id], Decimal("33.34"))
        self.assertEqual(sum(splits.values()), Decimal("100.00"))

        # Sum of % is not 100 (fails)
        invalid_pct = {
            self.payer.id: Decimal("33.00"),
            self.member1.id: Decimal("33.00"),
            self.member2.id: Decimal("33.00")
        }
        with self.assertRaises(ValidationError):
            compute_splits(self.expense_100, invalid_pct, self.members)

    def test_shares_split_proportional_and_rounding(self):
        """
        Why: Verifies SHARES proportional calculations and remainder cents allocations.
        
        Test Case: ₹100 split with shares: Payer (2), Member 1 (1), Member 2 (1). Total shares = 4.
        Payer: 100 * (2/4) = 50.00
        Member 1: 100 * (1/4) = 25.00
        Member 2: 100 * (1/4) = 25.00
        """
        self.expense_100.split_type = "SHARES"
        self.expense_100.save()
        
        shares_input = {
            self.payer.id: 2,
            self.member1.id: 1,
            self.member2.id: 1
        }
        splits = compute_splits(self.expense_100, shares_input, self.members)
        self.assertEqual(splits[self.payer.id], Decimal("50.00"))
        self.assertEqual(splits[self.member1.id], Decimal("25.00"))
        self.assertEqual(splits[self.member2.id], Decimal("25.00"))
        self.assertEqual(sum(splits.values()), Decimal("100.00"))


class ExpenseViewsIntegrationTests(TestCase):
    """
    Integration tests for Expense HTML template views.
    
    Why: Validates that recording expenses triggers split creation, redirects
    to detail pages, and renders splits accurately.
    """

    def setUp(self):
        """
        Why: Standard users authentication and paths mapping.
        """
        self.payer = User.objects.create_user(
            email="payer@example.com", name="Payer User", password="password123"
        )
        self.member1 = User.objects.create_user(
            email="m1@example.com", name="Member 1", password="password123"
        )
        self.client.login(username=self.payer.email, password="password123")
        
        self.group = Group.objects.create(name="Vacation Group", created_by=self.payer)
        # Setup memberships
        from groups.models import GroupMembership
        GroupMembership.objects.create(group=self.group, user=self.payer, joined_at=date(2026, 6, 1))
        GroupMembership.objects.create(group=self.group, user=self.member1, joined_at=date(2026, 6, 1))

        self.create_url = reverse('expense_create')

    def test_create_expense_view_post_success(self):
        """
        Why: Assures posting valid form details registers the expense and auto-creates splits.
        """
        post_data = {
            'group': self.group.id,
            'paid_by': self.payer.id,
            'description': 'Hotel booking',
            'date': '2026-06-01',
            'original_amount': '150.00',
            'original_currency': 'INR',
            'split_type': 'EQUAL'
        }
        
        # Act
        response = self.client.post(self.create_url, post_data)
        
        # Assert redirect to detail
        self.assertEqual(response.status_code, 302)
        expense = Expense.objects.get(description='Hotel booking')
        self.assertRedirects(response, reverse('expense_detail', args=[expense.id]))
        
        # Verify 2 splits are created (EQUAL ₹150 split between 2 users => ₹75.00 each)
        splits = ExpenseSplit.objects.filter(expense=expense)
        self.assertEqual(splits.count(), 2)
        for s in splits:
            self.assertEqual(s.share_amount_inr, Decimal("75.00"))

    def test_create_expense_view_post_invalid(self):
        """
        Why: Assures that posting invalid form data returns HTTP 200 and renders the form errors
        rather than raising AttributeError.
        """
        invalid_post_data = {
            'group': self.group.id,
            'paid_by': self.payer.id,
            'description': '',  # Invalid: empty description
            'date': '2026-06-01',
            'original_amount': '-10.00',
            'original_currency': 'INR',
            'split_type': 'EQUAL'
        }
        response = self.client.post(self.create_url, invalid_post_data)
        # Should stay on the form page and render form errors instead of raising 500 error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Failed to create expense. Please correct form validation errors.")
            
    def test_detail_view_displays_splits(self):
        """
        Why: Assures detail page presents user list and split amounts.
        """
        expense = Expense.objects.create(
            group=self.group,
            paid_by=self.payer,
            description="Taxi",
            date=date(2026, 6, 1),
            original_amount=Decimal("30.00"),
            original_currency="INR",
            split_type="EQUAL"
        )
        ExpenseSplit.objects.create(expense=expense, user=self.payer, share_amount_inr=Decimal("15.00"))
        ExpenseSplit.objects.create(expense=expense, user=self.member1, share_amount_inr=Decimal("15.00"))
        
        detail_url = reverse('expense_detail', args=[expense.id])
        response = self.client.get(detail_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Taxi")
        self.assertContains(response, "Payer User")
        self.assertContains(response, "15.00 INR")
