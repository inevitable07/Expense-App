from django.contrib import admin
from .models import Group, GroupMembership

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """
    Admin registration for the Group model.
    
    Why: Provides an interface in the admin panel to view, inspect,
    and manage expense sharing groups.
    """
    list_display = ('id', 'name', 'created_by', 'created_at')
    search_fields = ('name', 'created_by__email')
    list_filter = ('created_at',)

@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    """
    Admin registration for the GroupMembership model.
    
    Why: Provides an interface to inspect and manage historical and active
    memberships of users within groups.
    """
    list_display = ('id', 'group', 'user', 'joined_at', 'left_at')
    search_fields = ('group__name', 'user__email', 'user__name')
    list_filter = ('joined_at', 'left_at')
