from django.urls import path
from .views import SignUpView, CustomLoginView, CustomLogoutView

urlpatterns = [
    # Why: Routes requests for new user registration to the SignUpView.
    path('signup/', SignUpView.as_view(), name='signup'),
    
    # Why: Routes user credential submission and validation to the CustomLoginView.
    path('login/', CustomLoginView.as_view(), name='login'),
    
    # Why: Routes requests to terminate sessions and log out to the CustomLogoutView.
    path('logout/', CustomLogoutView.as_view(), name='logout'),
]
