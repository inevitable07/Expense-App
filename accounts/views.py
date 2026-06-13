from django.urls import reverse_lazy
from django.views import generic, View
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from .forms import CustomUserCreationForm, CustomAuthenticationForm

class SignUpView(generic.CreateView):
    """
    View to handle user signup registration.
    
    Why: Uses generic CreateView to serve the custom user creation form.
    On successful POST validation, the user is registered.
    """
    form_class = CustomUserCreationForm
    template_name = 'accounts/signup.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        """
        Why: Overrides standard success behavior to automatically log the user in
        immediately after signup, creating an active session and redirecting to home.
        """
        # Save user and get the user instance
        user = form.save()
        # Automatically login the user
        login(self.request, user)
        return HttpResponseRedirect(self.success_url)

class CustomLoginView(LoginView):
    """
    View to handle user login.
    
    Why: Subclasses built-in LoginView to integrate our CustomAuthenticationForm
    with Bootstrap classes and point to our styled login template.
    """
    form_class = CustomAuthenticationForm
    template_name = 'accounts/login.html'
    
    def get_success_url(self):
        """
        Why: Redirects authenticated users to the home dashboard upon success.
        """
        return reverse_lazy('home')

class CustomLogoutView(View):
    """
    View to handle user logout.
    
    Why: Extends base View to handle both GET and POST requests for logging out,
    clearing session store credentials, and redirecting the browser back to login.
    """
    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect('login')

    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect('login')
