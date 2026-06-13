from django import forms
from django.contrib.auth import get_user_model
from .models import Settlement
from groups.models import GroupMembership

User = get_user_model()

class SettlementForm(forms.ModelForm):
    """
    Form to record a direct payment settlement.

    Why: Captures settlement fields, applies Bootstrap layout styling,
    and dynamically restricts paid_by and paid_to querysets to members
    of the chosen group to ensure domain boundary integrity.
    """
    class Meta:
        model = Settlement
        fields = ['group', 'paid_by', 'paid_to', 'amount_inr', 'date', 'note']
        widgets = {
            'group': forms.Select(attrs={'class': 'form-select', 'id': 'id_group'}),
            'paid_by': forms.Select(attrs={'class': 'form-select', 'id': 'id_paid_by'}),
            'paid_to': forms.Select(attrs={'class': 'form-select', 'id': 'id_paid_to'}),
            'amount_inr': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00',
                'id': 'id_amount_inr'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'id': 'id_date'
            }),
            'note': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional reference details (e.g. UPI txn ID, Bank transaction)',
                'id': 'id_note'
            }),
        }

    def __init__(self, *args, **kwargs):
        """
        Why: Restricts paid_by and paid_to to users who are members of the group.
        If a group_id is supplied initially or submitted via POST data,
        only the members of that group will be available as choices.
        """
        group_id = kwargs.pop('group_id', None)
        super().__init__(*args, **kwargs)

        selected_group_id = group_id or self.initial.get('group')
        # If POST data has group, use it for filtering
        if args and len(args) > 0 and isinstance(args[0], dict) and 'group' in args[0]:
            selected_group_id = args[0].get('group')
        elif self.data and 'group' in self.data:
            selected_group_id = self.data.get('group')

        if selected_group_id:
            try:
                selected_group_id = int(selected_group_id)
                member_ids = GroupMembership.objects.filter(group_id=selected_group_id).values_list('user_id', flat=True)
                self.fields['paid_by'].queryset = User.objects.filter(id__in=member_ids)
                self.fields['paid_to'].queryset = User.objects.filter(id__in=member_ids)
            except (ValueError, TypeError):
                # Fallback to no users if group ID is malformed
                self.fields['paid_by'].queryset = User.objects.none()
                self.fields['paid_to'].queryset = User.objects.none()
