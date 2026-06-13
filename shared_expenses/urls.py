"""
URL configuration for shared_expenses project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    # Why: Routes to administrative portal.
    path('admin/', admin.site.urls),
    
    # Why: Includes all user registration and authentication endpoints.
    path('accounts/', include('accounts.urls')),
    
    # Why: Routes to groups and memberships API endpoints/template views.
    path('', include('groups.urls')),
    
    # Why: Routes to expenses creation and detail views.
    path('', include('expenses.urls')),
    
    # Why: Routes to balance summary, detail breakdown, and simplified debts views.
    path('', include('balances.urls')),
    
    # Why: Main application dashboard / home landing page.
    path('', TemplateView.as_view(template_name='accounts/home.html'), name='home'),
]
