from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GroupViewSet, 
    GroupListView, 
    GroupCreateView, 
    GroupDetailView, 
    GroupAddMemberView, 
    GroupRemoveMemberView
)

# Initialize DefaultRouter for Group API
router = DefaultRouter()
# Why: Exposes standard DRF endpoints for groups (e.g. GET /api/groups/, POST /api/groups/, etc.)
router.register(r'groups', GroupViewSet, basename='group')

urlpatterns = [
    # Why: Groups all DRF API endpoints under the api/ namespace prefix.
    path('api/', include(router.urls)),
    
    # HTML Template views for user interactive sessions
    # Why: Routes requests to display the user's groups.
    path('groups/', GroupListView.as_view(), name='group_list'),
    
    # Why: Routes requests to create a new group.
    path('groups/create/', GroupCreateView.as_view(), name='group_create'),
    
    # Why: Routes requests to view details of a specific group.
    path('groups/<int:pk>/', GroupDetailView.as_view(), name='group_detail'),
    
    # Why: Routes POST requests to add a member to a group.
    path('groups/<int:pk>/add-member/', GroupAddMemberView.as_view(), name='group_add_member'),
    
    # Why: Routes POST requests to remove a member from a group.
    path('groups/<int:pk>/remove-member/', GroupRemoveMemberView.as_view(), name='group_remove_member'),
]
