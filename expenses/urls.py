from django.urls import path
from .views import ExpenseCreateView, ExpenseDetailView

urlpatterns = [
    # Why: Routes to the HTML page to record a new group expense.
    path('expenses/create/', ExpenseCreateView.as_view(), name='expense_create'),
    
    # Why: Routes to the drill-down detail view displaying total cost and user split shares.
    path('expenses/<int:pk>/', ExpenseDetailView.as_view(), name='expense_detail'),
]
