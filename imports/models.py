from django.db import models
from django.conf import settings

class ImportBatch(models.Model):
    """
    Tracks uploaded batches of data (such as CSV files) to be imported.

    Why: Serves as an audit trail wrapper. All imported expenses will hold a
    ForeignKey to their import batch to allow lineage tracing.
    """

    STATUS_CHOICES = [
        ('PENDING_REVIEW', 'Pending Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PARTIALLY_APPLIED', 'Partially Applied'),
    ]

    # Why: Automatically tracks when the import batch file was uploaded.
    # We allow null=True to avoid database migration conflicts with legacy placeholder records.
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        null=True,
        blank=True,
        verbose_name="Uploaded At",
        help_text="Timestamp when the file was uploaded."
    )

    # Why: Keeps track of the user who performed the upload for audit purposes.
    # We allow null=True to avoid database migration conflicts with legacy placeholder records.
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='uploaded_batches',
        verbose_name="Uploaded By",
        help_text="The user who uploaded this batch."
    )

    # Why: Links the import to a specific group where the expenses should be recorded.
    # We allow null=True to avoid database migration conflicts with legacy placeholder records.
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='import_batches',
        verbose_name="Group",
        help_text="The group where this import will be applied."
    )

    # Why: Tracks the review and approval status of the batch (Meera's approval gate).
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='PENDING_REVIEW',
        verbose_name="Status",
        help_text="The current validation or approval status of this import batch."
    )

    # Why: Stores the uploaded file so it can be re-parsed or archived for audits.
    raw_file = models.FileField(
        upload_to='import_raw_files/',
        blank=True,
        null=True,
        verbose_name="Raw File",
        help_text="The uploaded CSV/JSON file."
    )

    # Why: Retaining the description field from the original placeholder to avoid breaking queries.
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Description",
        help_text="Optional description or metadata regarding this import batch."
    )

    def __str__(self):
        """
        Why: Returns string representation showing the batch ID and its current status.
        """
        return f"Import Batch #{self.id} ({self.status}) - {self.uploaded_at.strftime('%Y-%m-%d %H:%M')}"


class ImportAnomaly(models.Model):
    """
    Represents an individual anomaly or data conflict flagged during import parsing.

    Why: The importer must never silently correct/fix data. Recording anomalies
    individually allows human review, approval, rejection, or modification before applying changes.
    """

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('MODIFIED', 'Modified'),
    ]

    # Why: Links the anomaly back to its parent import batch execution.
    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name='anomalies',
        verbose_name="Import Batch",
        help_text="The import batch this anomaly belongs to."
    )

    # Why: Identifies where the anomaly occurred in the source file (e.g. "row 14") for traceability.
    row_reference = models.CharField(
        max_length=100,
        verbose_name="Row Reference",
        help_text="Reference to the row in the source file (e.g., 'row 14')."
    )

    # Why: Classification of the error/conflict (e.g. 'DUPLICATE_ROW', 'NEGATIVE_AMOUNT', 'REVIEW_REQUIRED').
    anomaly_type = models.CharField(
        max_length=100,
        verbose_name="Anomaly Type",
        help_text="The category of anomaly detected."
    )

    # Why: Plain English description explaining what went wrong.
    description = models.TextField(
        verbose_name="Description",
        help_text="Explanation of the detected data anomaly."
    )

    # Why: Preserves the exact raw row dictionary from the parser for full audit and reconstruction.
    raw_row_data = models.JSONField(
        verbose_name="Raw Row Data",
        help_text="The original raw fields and values parsed from this row."
    )

    # Why: Algorithmic recommendation to assist the reviewer (e.g., 'Skip row', 'Absolute value').
    suggested_action = models.TextField(
        verbose_name="Suggested Action",
        help_text="Automated suggested resolution for this anomaly."
    )

    # Why: Captures manual corrections or overrides input during Meera's review phase.
    final_action = models.TextField(
        blank=True,
        null=True,
        verbose_name="Final Action",
        help_text="The final resolution action applied by the reviewer."
    )

    # Why: Tracks the decision state of this anomaly.
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='PENDING',
        verbose_name="Status",
        help_text="The current review decision state of this anomaly."
    )

    def __str__(self):
        """
        Why: Returns string representation of the anomaly.
        """
        return f"{self.row_reference} [{self.anomaly_type}]: {self.status}"
