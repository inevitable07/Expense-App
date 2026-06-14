from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction

from .models import ImportBatch, ImportAnomaly
from .forms import CSVUploadForm
from .pipeline import run_import
from groups.models import Group

class ImportUploadView(LoginRequiredMixin, View):
    """
    View to upload a raw CSV expense file.

    Why: Serves as the initial step in the import workflow. Triggers the
    run_import parser pipeline, wrapping file uploads with group scoping.
    """

    def get(self, request, group_id):
        """
        Why: Renders the file selection form scoped to the selected group.
        """
        group = get_object_or_404(Group, pk=group_id)
        form = CSVUploadForm()
        return render(request, 'imports/import_upload.html', {
            'form': form,
            'group': group
        })

    def post(self, request, group_id):
        """
        Why: Triggers the parsing, detection, and batch logging pipeline on POST.
        """
        group = get_object_or_404(Group, pk=group_id)
        form = CSVUploadForm(request.POST, request.FILES)

        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                # Run the pipeline to populate ImportBatch and detect anomalies
                batch = run_import(csv_file, group, request.user)
                messages.success(request, "File parsed and processed. Please review detected anomalies below.")
                return redirect('import_review', batch_id=batch.id)
            except Exception as e:
                messages.error(request, f"Failed to process import: {str(e)}")
        
        return render(request, 'imports/import_upload.html', {
            'form': form,
            'group': group
        })


class ImportReviewView(LoginRequiredMixin, DetailView):
    """
    View to review and resolve flagged anomalies (Meera's approval gate).

    Why: Implements the 'pipeline: Detect -> Review -> Approve -> Apply' mandate.
    The importer never automatically corrects data, requiring explicit user decisions
    (Approve, Reject, or Modify) per anomaly.
    """
    model = ImportBatch
    pk_url_kwarg = 'batch_id'
    template_name = 'imports/import_review.html'
    context_object_name = 'batch'

    def get_context_data(self, **kwargs):
        """
        Why: Adds all flagged anomalies to context sorted by row reference index for clear reading.
        """
        context = super().get_context_data(**kwargs)
        context['anomalies'] = self.object.anomalies.order_by('row_reference')
        return context

    def post(self, request, batch_id):
        """
        Why: Saves the reviewer's decisions on each anomaly. Updates anomaly statuses
        and batch status under an atomic transaction.
        """
        batch = get_object_or_404(ImportBatch, pk=batch_id)
        anomalies = batch.anomalies.all()

        with transaction.atomic():
            for anomaly in anomalies:
                # Why: Read the decision values submitted from the form inputs
                status_key = f"status_{anomaly.id}"
                action_key = f"final_action_{anomaly.id}"

                submitted_status = request.POST.get(status_key)
                submitted_action = request.POST.get(action_key, "")

                # Why: Only update if the status matches valid database choices
                if submitted_status in ['APPROVED', 'REJECTED', 'MODIFIED']:
                    anomaly.status = submitted_status
                    anomaly.final_action = submitted_action
                    anomaly.save()

            # Why: Mark batch as approved now that decisions have been committed.
            # (Note: Actual application logic to generate Expenses/Settlements
            # will be integrated in the next prompt phase).
            batch.status = 'APPROVED'
            batch.save()

        messages.success(request, "Your decisions have been saved successfully.")
        return redirect('import_review', batch_id=batch.id)
