from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    """
    Form for registering a new User with email and name.
    
    Why: Inherits from Django's UserCreationForm to leverage built-in secure password
    validation, generation, and confirmation logic. It overrides Meta to expose
    only the email and name fields, aligning with our email-only authentication model.
    """
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email', 'name')

    def __init__(self, *args, **kwargs):
        """
        Why: Enhances standard form field rendering by applying Bootstrap classes
        and custom placeholders, avoiding styling markup in HTML templates.
        """
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
            
        self.fields['email'].widget.attrs.update({'placeholder': 'name@example.com'})
        self.fields['name'].widget.attrs.update({'placeholder': 'Full Name'})

class CustomAuthenticationForm(AuthenticationForm):
    """
    Form for logging in an existing User.
    
    Why: Customizes Django's default AuthenticationForm so that the login prompt
    reads 'Email' rather than 'Username', adjusting labels and applying Bootstrap
    design properties to input fields.
    """
    username = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'name@example.com',
            'autofocus': True
        })
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )
