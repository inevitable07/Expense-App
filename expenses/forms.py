from django import forms
from django.contrib.auth import get_user_model
from .models import Expense

User = get_user_model()

class ExpenseForm(forms.ModelForm):
    """
    Form to capture expense transactions.
    
    Why: Renders fields with Bootstrap classes and validates that mandatory
    parameters are supplied by the user during manual entry.
    """
    class Meta:
        model = Expense
        fields = [
            'group', 
            'paid_by', 
            'description', 
            'date', 
            'original_amount', 
            'original_currency', 
            'fx_rate_used', 
            'split_type'
        ]
        widgets = {
            'group': forms.Select(attrs={'class': 'form-select'}),
            'paid_by': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g. Pizza Night, Cab Fare'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control', 
                'type': 'date'
            }),
            'original_amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'original_currency': forms.Select(attrs={'class': 'form-select'}),
            'fx_rate_used': forms.Select(attrs={'class': 'form-select'}),
            'split_type': forms.Select(attrs={'class': 'form-select'}),
        }
