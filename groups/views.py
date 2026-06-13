from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
from django.views.generic import ListView, DetailView, CreateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse_lazy

from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Group, GroupMembership
from .serializers import (
    GroupSerializer, 
    GroupMembershipSerializer, 
    AddMemberSerializer, 
    RemoveMemberSerializer
)
from .forms import GroupForm, AddMemberForm, RemoveMemberForm

User = get_user_model()

# =====================================================================
# Django REST Framework API Views
# =====================================================================

class GroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet to manage Group records and membership transitions.
    
    Why: Handles REST requests for Group creation, retrieval, updates,
    and exposes actions for membership lifecycle management.
    """
    queryset = Group.objects.all().order_by('-created_at')
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        """
        Why: Automatically sets the group creator (created_by) to the requesting user
        and creates an initial active GroupMembership starting on the creation date.
        """
        group = serializer.save(created_by=self.request.user)
        
        # Automatically enroll the creator as an active member starting today
        GroupMembership.objects.create(
            group=group,
            user=self.request.user,
            joined_at=timezone.now().date()
        )

    @action(detail=True, methods=['post'], url_path='add-member')
    def add_member(self, request, pk=None):
        """
        Why: Invites/adds a member to the group with a specified joined_at date.
        Enforces date constraints and prevents overlapping membership windows.
        """
        group = self.get_object()
        serializer = AddMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_email = serializer.validated_data['email']
        joined_at = serializer.validated_data['joined_at']
        user = User.objects.get(email=user_email)

        try:
            membership = GroupMembership(
                group=group,
                user=user,
                joined_at=joined_at
            )
            membership.save()
            
            return Response(
                GroupMembershipSerializer(membership).data,
                status=status.HTTP_201_CREATED
            )
        except DjangoValidationError as e:
            # Why: Converts Django core ValidationError to DRF validation exception
            # so that HTTP 400 Bad Request is correctly returned to API client.
            raise serializers.ValidationError(detail=e.message_dict if hasattr(e, 'message_dict') else str(e))

    @action(detail=True, methods=['post'], url_path='remove-member')
    def remove_member(self, request, pk=None):
        """
        Why: Sets a leave date (left_at) for an active user membership in the group.
        """
        group = self.get_object()
        serializer = RemoveMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_email = serializer.validated_data['email']
        left_at = serializer.validated_data['left_at']
        user = User.objects.get(email=user_email)

        # Look up active membership
        try:
            membership = GroupMembership.objects.get(
                group=group,
                user=user,
                left_at__isnull=True
            )
        except GroupMembership.DoesNotExist:
            raise serializers.ValidationError(
                {"email": "This user does not have an active membership in this group."}
            )

        try:
            membership.left_at = left_at
            membership.save()
            return Response(
                GroupMembershipSerializer(membership).data,
                status=status.HTTP_200_OK
            )
        except DjangoValidationError as e:
            raise serializers.ValidationError(detail=e.message_dict if hasattr(e, 'message_dict') else str(e))

    @action(detail=True, methods=['get'], url_path='members')
    def list_members(self, request, pk=None):
        """
        Why: Lists all historical and active memberships for a specific group.
        """
        group = self.get_object()
        memberships = group.memberships.all().order_by('joined_at')
        serializer = GroupMembershipSerializer(memberships, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# =====================================================================
# Standard Django HTML Template Views
# =====================================================================

class GroupListView(LoginRequiredMixin, ListView):
    """
    Template view to display all groups a user is (or was) registered in.
    
    Why: Provides a clean web page listing active and past groups.
    """
    model = Group
    template_name = 'groups/group_list.html'
    context_object_name = 'groups'

    def get_queryset(self):
        """
        Why: Filters groups to only return those where the logged-in user holds
        a valid membership.
        """
        return Group.objects.filter(memberships__user=self.request.user).distinct().order_by('-created_at')

class GroupCreateView(LoginRequiredMixin, CreateView):
    """
    Template view to support new Group creation.
    
    Why: Serves the group creation form and auto-enrolls the creator on success.
    """
    model = Group
    form_class = GroupForm
    template_name = 'groups/group_form.html'
    success_url = reverse_lazy('group_list')

    def form_valid(self, form):
        """
        Why: Attaches the logged-in user as creator and registers their membership.
        """
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # Automatically enroll creator starting today
        GroupMembership.objects.create(
            group=self.object,
            user=self.request.user,
            joined_at=timezone.now().date()
        )
        messages.success(self.request, f"Group '{self.object.name}' was created successfully!")
        return response

class GroupDetailView(LoginRequiredMixin, DetailView):
    """
    Template view presenting details, memberships list, and invitation forms of a Group.
    
    Why: Acts as the central administration dashboard for group members.
    """
    model = Group
    template_name = 'groups/group_detail.html'
    context_object_name = 'group'

    def get_context_data(self, **kwargs):
        """
        Why: Appends the membership history, adding/removing member forms, and
        the list of associated group expenses to the template context.
        """
        context = super().get_context_data(**kwargs)
        context['memberships'] = self.object.memberships.all().order_by('joined_at')
        context['add_member_form'] = AddMemberForm()
        context['remove_member_form'] = RemoveMemberForm()
        context['today'] = timezone.now().date()
        # Why: Retrieves all expenses related to the group, ordered newest first,
        # so they can be rendered in the group details dashboard.
        context['expenses'] = self.object.expenses.all().order_by('-date', '-id')
        return context

class GroupAddMemberView(LoginRequiredMixin, View):
    """
    POST view handling user addition to a group.
    
    Why: Validates inputs, attempts database creation of GroupMembership,
    and returns feedback messages to the user.
    """
    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        form = AddMemberForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            joined_at = form.cleaned_data['joined_at']
            user = User.objects.get(email=email)
            try:
                membership = GroupMembership(
                    group=group,
                    user=user,
                    joined_at=joined_at
                )
                membership.save()
                messages.success(request, f"Successfully added {user.name} ({email}) to the group.")
            except DjangoValidationError as e:
                # Handle model validation errors (overlaps, etc.)
                error_msg = "; ".join([f"{v[0]}" for k, v in e.message_dict.items()]) if hasattr(e, 'message_dict') else str(e)
                messages.error(request, f"Failed to add member: {error_msg}")
        else:
            messages.error(request, f"Validation error: {form.errors.as_text()}")
        return redirect('group_detail', pk=pk)

class GroupRemoveMemberView(LoginRequiredMixin, View):
    """
    POST view handling setting a leave date for active group members.
    
    Why: Updates left_at attribute for the user's active membership record.
    """
    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        form = RemoveMemberForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            left_at = form.cleaned_data['left_at']
            user = User.objects.get(email=email)
            try:
                membership = GroupMembership.objects.get(
                    group=group,
                    user=user,
                    left_at__isnull=True
                )
                membership.left_at = left_at
                membership.save()
                messages.success(request, f"Successfully marked {user.name} ({email}) as left.")
            except GroupMembership.DoesNotExist:
                messages.error(request, f"User {email} does not have an active membership in this group.")
            except DjangoValidationError as e:
                error_msg = "; ".join([f"{v[0]}" for k, v in e.message_dict.items()]) if hasattr(e, 'message_dict') else str(e)
                messages.error(request, f"Failed to mark member as left: {error_msg}")
        else:
            messages.error(request, f"Validation error: {form.errors.as_text()}")
        return redirect('group_detail', pk=pk)
