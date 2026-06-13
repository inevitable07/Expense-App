from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import Group

User = get_user_model()

class GroupForm(forms.ModelForm):
    """
    Form to create a new expense sharing group.
    
    Why: Binds user input directly to the Group model name attribute.
    """
    class Meta:
        model = Group
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Roommates Flat 4B, Summer Road Trip'
            })
        }

class AddMemberForm(forms.Form):
    """
    Form to invite/add a member to a group using their email.
    
    Why: Validates that the email belongs to a registered user and
    captures the date they joined the group.
    """
    email = forms.EmailField(
        label="Member Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'name@example.com'
        })
    )
    joined_at = forms.DateField(
        label="Join Date",
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    def clean_email(self):
        """
        Why: Rejects form submissions if the email doesn't correspond to any registered user.
        """
        email = self.cleaned_data.get('email')
        if not User.objects.filter(email=email).exists():
            raise ValidationError("No user registered with this email address.")
        return email

class RemoveMemberForm(forms.Form):
    """
    Form to set a leave date (left_at) for an active group member.
    
    Why: Captures the leaving date to close out their active membership window.
    """
    email = forms.EmailField(
        widget=forms.HiddenInput()
    )
    left_at = forms.DateField(
        label="Leave Date",
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
