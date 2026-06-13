from django.urls import path
from .views import GroupBalanceSummaryView, BalanceDetailView, SimplifiedDebtsView

urlpatterns = [
    # Why: Routes to the group-level balance summary showing net balance per member.
    path(
        'balances/group/<int:pk>/',
        GroupBalanceSummaryView.as_view(),
        name='group_balance_summary'
    ),

    # Why: Routes to the individual member balance detail page showing
    # line-by-line breakdown of credits and debits (Rohan's drill-down).
    path(
        'balances/group/<int:group_pk>/user/<int:user_pk>/',
        BalanceDetailView.as_view(),
        name='balance_detail'
    ),

    # Why: Routes to the simplified "who pays whom" summary page
    # showing minimized settlement transactions (Aisha's requirement).
    path(
        'balances/group/<int:pk>/simplified/',
        SimplifiedDebtsView.as_view(),
        name='simplified_debts'
    ),
]
