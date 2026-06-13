from django.db import models

class ImportBatch(models.Model):
    """
    Placeholder model for tracking data import batches (CSV/JSON file uploads).
    
    Why: Serves as a target ForeignKey references in Expense models to preserve
    lineage and auditability of imported entries before full import features are coded.
    """
    
    # Why: Automatically logs the date and time when the import was executed.
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Imported At",
        help_text="Timestamp when this batch was imported."
    )
    
    # Why: Optional notes or name of the file imported for context.
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Description",
        help_text="Optional description or original file name of the import batch."
    )

    def __str__(self):
        """
        Why: Returns string representation of ImportBatch displaying its ID and creation date.
        """
        return f"Import Batch #{self.id} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
