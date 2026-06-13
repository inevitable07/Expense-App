from django.urls import path
from .views import SettlementCreateView, SettlementListView

urlpatterns = [
    # Why: Routes to the HTML form view to record a new direct settlement payment.
    path(
        'settlements/create/',
        SettlementCreateView.as_view(),
        name='settlement_create'
    ),

    # Why: Routes to the chronological settlements list view scoped to a specific group.
    path(
        'groups/<int:group_id>/settlements/',
        SettlementListView.as_view(),
        name='settlement_list'
    ),
]
