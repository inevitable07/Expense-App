from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.views.generic import DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.contrib import messages
from django.urls import reverse

from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Expense, ExpenseSplit
from .forms import ExpenseForm
from .services import compute_splits
from groups.models import Group, GroupMembership
from django.db.models import Q

# =====================================================================
# SECTION 5: VIEW IMPLEMENTATIONS
# =====================================================================

class ExpenseCreateView(LoginRequiredMixin, CreateView):
    """
    Template view to create a new Expense.
    
    Why: Handles GET to show the expense form (with active members payload)
    and POST to parse, compute, and save splits inside an atomic transaction.
    """
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'

    def get_initial(self):
        """
        Why: Pre-populates the group field if group id is passed as a GET query parameter.
        """
        initial = super().get_initial()
        group_id = self.request.GET.get('group')
        if group_id:
            initial['group'] = group_id
        return initial

    def get_context_data(self, **kwargs):
        """
        Why: Adds active memberships map to context so the frontend JavaScript
        can dynamically present split inputs depending on chosen group and date.
        """
        context = super().get_context_data(**kwargs)
        # Fetch all memberships to serialize for dynamic JS split grids
        memberships = GroupMembership.objects.select_related('user', 'group').all()
        
        # Structure memberships as group_id -> list of members with joined/left date bounds
        group_members_data = {}
        for m in memberships:
            group_members_data.setdefault(m.group_id, []).append({
                'id': m.user.id,
                'name': m.user.name,
                'email': m.user.email,
                'joined_at': m.joined_at.isoformat(),
                'left_at': m.left_at.isoformat() if m.left_at else None
            })
            
        context['group_members_json'] = group_members_data
        context['today'] = timezone.now().date().isoformat()
        return context

    def post(self, request, *args, **kwargs):
        """
        Why: Overrides POST to handle custom splits inputs dynamically and execute
        splits calculations under an atomic transaction boundary.
        """
        self.object = None
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            
            # Retrieve date and group parameters
            expense_date = form.cleaned_data['date']
            group = form.cleaned_data['group']
            
            # Why: Queries all active members in the group on the specific transaction date.
            active_memberships = GroupMembership.objects.filter(
                group=group,
                joined_at__lte=expense_date
            ).filter(
                Q(left_at__isnull=True) | Q(left_at__gte=expense_date)
            )
            active_members = [m.user for m in active_memberships]

            if not active_members:
                messages.error(request, "No active members found in this group on the specified date.")
                return self.form_invalid(form)

            # Why: Extracts split inputs from POST variables (names matching split_val_<user_id>).
            split_input = {}
            for key, value in request.POST.items():
                if key.startswith('split_val_') and value:
                    try:
                        user_id = int(key.replace('split_val_', ''))
                        split_input[user_id] = value
                    except ValueError:
                        pass

            try:
                # Why: Wraps database saving of Expense and its splits in an atomic transaction
                # to prevent partial database persistence.
                with transaction.atomic():
                    # Triggers clean() which calculates amount_inr and validates FX rates
                    expense.full_clean()
                    expense.save()
                    
                    # Computes shares mapping using split service engine
                    splits = compute_splits(expense, split_input, active_members)
                    
                    # Persists each calculated split record
                    for user_id, share in splits.items():
                        ExpenseSplit.objects.create(
                            expense=expense,
                            user_id=user_id,
                            share_amount_inr=share
                        )
                
                messages.success(request, "Expense and split details created successfully.")
                return redirect('expense_detail', pk=expense.id)
                
            except DjangoValidationError as e:
                # Extract clean error messages
                error_msg = "; ".join([f"{k}: {v[0]}" for k, v in e.message_dict.items()]) if hasattr(e, 'message_dict') else str(e)
                messages.error(request, f"Calculation or model error: {error_msg}")
                return self.form_invalid(form)
        else:
            messages.error(request, "Failed to create expense. Please correct form validation errors.")
            return self.form_invalid(form)

class ExpenseDetailView(LoginRequiredMixin, DetailView):
    """
    Template view to display Expense details.
    
    Why: Provides a drill-down view showing parent expense fields and
    the list of associated ExpenseSplit rows (showing who owes what).
    """
    model = Expense
    template_name = 'expenses/expense_detail.html'
    context_object_name = 'expense'

    def get_context_data(self, **kwargs):
        """
        Why: Adds list of splits to context for rendering.
        """
        context = super().get_context_data(**kwargs)
        context['splits'] = self.object.splits.select_related('user').all()
        return context
