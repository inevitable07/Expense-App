from django.views.generic import DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from groups.models import Group
from .engine import get_group_balances, get_balance_breakdown, simplify_debts

User = get_user_model()


class GroupBalanceSummaryView(LoginRequiredMixin, DetailView):
    """
    Template view displaying the net balance of every member in a group.

    Why: Provides a financial snapshot showing who is owed money and who
    owes money within the group, with links to individual drill-down
    and simplified debt resolution.
    """
    model = Group
    template_name = 'balances/group_balances.html'
    context_object_name = 'group'

    def get_context_data(self, **kwargs):
        """
        Why: Computes per-member net balances and passes them to the template
        as a list of (user, balance) tuples sorted by balance descending
        (largest creditor first).
        """
        context = super().get_context_data(**kwargs)
        balances = get_group_balances(self.object)

        # Why: Sort by balance descending so creditors appear at top,
        # debtors at bottom — intuitive visual ordering.
        sorted_balances = sorted(
            balances.items(),
            key=lambda x: x[1],
            reverse=True
        )
        context['balances'] = sorted_balances
        return context


class BalanceDetailView(LoginRequiredMixin, TemplateView):
    """
    Template view displaying the line-by-line breakdown of a user's
    balance within a group.

    Why: Enables drill-down from a summary balance number to every
    individual ExpenseSplit and Settlement record that composes it.
    Each row is traceable to a specific database record.
    """
    template_name = 'balances/balance_detail.html'

    def get_context_data(self, **kwargs):
        """
        Why: Fetches the balance breakdown rows and computes the net
        total for display alongside the line-by-line audit trail.
        """
        context = super().get_context_data(**kwargs)
        group = get_object_or_404(Group, pk=self.kwargs['group_pk'])
        member = get_object_or_404(User, pk=self.kwargs['user_pk'])

        breakdown = get_balance_breakdown(member, group)

        # Why: Compute net total from breakdown rows to verify it matches
        # the summary balance. This provides a consistency check.
        from decimal import Decimal
        net_total = sum(row['amount'] for row in breakdown) if breakdown else Decimal('0.00')

        context['group'] = group
        context['member'] = member
        context['breakdown'] = breakdown
        context['net_total'] = net_total
        return context


class SimplifiedDebtsView(LoginRequiredMixin, DetailView):
    """
    Template view displaying the simplified "who pays whom" transactions.

    Why: Reduces the complex web of individual debts into a minimal
    set of payment instructions. This is Aisha's "one number per person,
    who pays whom" requirement.
    """
    model = Group
    template_name = 'balances/simplified_debts.html'
    context_object_name = 'group'

    def get_context_data(self, **kwargs):
        """
        Why: Runs the greedy debt simplification algorithm and passes
        the resulting (from_user, to_user, amount) transactions to
        the template for display.
        """
        context = super().get_context_data(**kwargs)
        transactions = simplify_debts(self.object)
        context['transactions'] = transactions
        return context
