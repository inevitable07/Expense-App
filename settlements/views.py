import json
from django.views.generic import CreateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone

from .models import Settlement
from .forms import SettlementForm
from groups.models import Group, GroupMembership

class SettlementCreateView(LoginRequiredMixin, CreateView):
    """
    Template view to record a new direct payment settlement.

    Why: Allows users to input settlement payments, performs dynamic
    validation, and provides member lists for interactive drop-downs.
    """
    model = Settlement
    form_class = SettlementForm
    template_name = 'settlements/settlement_form.html'

    def get_initial(self):
        """
        Why: Pre-populates the group field if a group ID is supplied as a GET query parameter.
        """
        initial = super().get_initial()
        group_id = self.request.GET.get('group')
        if group_id:
            initial['group'] = group_id
        return initial

    def get_form_kwargs(self):
        """
        Why: Directs the form class to narrow choice querysets when a group is preselected.
        """
        kwargs = super().get_form_kwargs()
        group_id = self.request.GET.get('group') or self.request.POST.get('group')
        if group_id:
            kwargs['group_id'] = group_id
        return kwargs

    def get_context_data(self, **kwargs):
        """
        Why: Passes group membership data serialized as JSON so the client-side
        JavaScript can update select menus instantly on selection changes.
        """
        context = super().get_context_data(**kwargs)
        memberships = GroupMembership.objects.select_related('user', 'group').all()

        # Serialize memberships as {group_id: [{'id': id, 'name': name, 'email': email}, ...]}
        group_members = {}
        for m in memberships:
            group_members.setdefault(m.group_id, []).append({
                'id': m.user.id,
                'name': m.user.name,
                'email': m.user.email,
            })

        context['group_members_json'] = json.dumps(group_members)
        context['today'] = timezone.now().date().isoformat()

        # Supply preselected group metadata if applicable
        group_id = self.request.GET.get('group')
        if group_id:
            try:
                context['preselected_group'] = Group.objects.get(pk=group_id)
            except Group.DoesNotExist:
                pass

        return context

    def get_success_url(self):
        """
        Why: Redirects back to the group's chronological settlement list view.
        """
        return reverse('settlement_list', kwargs={'group_id': self.object.group.pk})

    def form_valid(self, form):
        """
        Why: Injects standard success notifications.
        """
        messages.success(self.request, "Settlement payment recorded successfully.")
        return super().form_valid(form)


class SettlementListView(LoginRequiredMixin, ListView):
    """
    Displays a list of all recorded settlement payments within a group.

    Why: Provides chronological audit trails for settlements (separate from expenses).
    """
    model = Settlement
    template_name = 'settlements/settlement_list.html'
    context_object_name = 'settlements'

    def get_queryset(self):
        """
        Why: Scope lists to a specific group ID, sorted chronologically ascending.
        """
        self.group = get_object_or_404(Group, pk=self.kwargs['group_id'])
        return Settlement.objects.filter(group=self.group).select_related('paid_by', 'paid_to').order_by('date')

    def get_context_data(self, **kwargs):
        """
        Why: Exposes group metadata to render correct titles and navigation links.
        """
        context = super().get_context_data(**kwargs)
        context['group'] = self.group
        return context
