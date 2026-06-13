from django.contrib import admin
from .models import Expense, ExpenseSplit

class ExpenseSplitInline(admin.TabularInline):
    """
    Inline edit definition for ExpenseSplit models.
    
    Why: Shows split share details directly inside the parent Expense admin page.
    """
    model = ExpenseSplit
    extra = 0

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    """
    Admin registration for Expense model.
    
    Why: Provides list, filter, search, and nested split configurations for expenses.
    """
    list_display = (
        'id', 
        'description', 
        'group', 
        'paid_by', 
        'original_amount', 
        'original_currency', 
        'amount_inr', 
        'split_type', 
        'status', 
        'date'
    )
    search_fields = ('description', 'group__name', 'paid_by__email', 'paid_by__name')
    list_filter = ('split_type', 'status', 'original_currency', 'date')
    inlines = [ExpenseSplitInline]

@admin.register(ExpenseSplit)
class ExpenseSplitAdmin(admin.ModelAdmin):
    """
    Admin registration for ExpenseSplit model.
    
    Why: Allows lookup and audits of individual user split allocations.
    """
    list_display = ('id', 'expense', 'user', 'share_amount_inr')
    search_fields = ('expense__description', 'user__email', 'user__name')
