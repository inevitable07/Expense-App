from django.db import transaction
from django.core.files.base import ContentFile
from .models import ImportBatch, ImportAnomaly
from .parser import parse_csv
from .detectors.example_detectors import DuplicateRowDetector, NegativeAmountDetector

def get_detectors():
    """
    Returns a list of all active anomaly detector instances.

    Why: Provides a centralized registry to easily plug and play new anomaly types
    (e.g., adding a 13th anomaly type in a live session).
    """
    return [
        DuplicateRowDetector(),
        NegativeAmountDetector(),
    ]

def run_import(file_obj, group, user) -> ImportBatch:
    """
    Parses a CSV file, runs all active detectors, and records the batch + anomalies.

    Why: The importer must never silently correct errors. Every conflict is logged
    as an ImportAnomaly record to be resolved later during Meera's approval gate phase.
    Does not create any Expense or Settlement records yet.

    Parameters:
        file_obj: A file-like object or UploadedFile containing CSV records.
        group: The Group instance this batch is uploaded to.
        user: The User instance uploading this batch.

    Returns:
        ImportBatch: The newly created batch record, set in PENDING_REVIEW state.
    """
    # Why: Parse raw CSV rows first to collect list of dicts with line number pointers
    rows = parse_csv(file_obj)

    # Why: Run each registered detector and aggregate all anomalies found
    all_anomalies = []
    for detector in get_detectors():
        detected_anomalies = detector.detect(rows)
        # Why: In case detector returns details missing anomaly_type, inject it
        for anomaly in detected_anomalies:
            if 'anomaly_type' not in anomaly:
                anomaly['anomaly_type'] = detector.anomaly_type
        all_anomalies.extend(detected_anomalies)

    # Why: Wrap the batch and anomaly creation inside a transaction.atomic block to prevent half-saved states
    with transaction.atomic():
        batch = ImportBatch.objects.create(
            uploaded_by=user,
            group=group,
            status='PENDING_REVIEW',
            description=getattr(file_obj, 'name', 'Uploaded File')
        )

        # Why: Save the uploaded raw file for audit trails and tracing
        if hasattr(file_obj, 'read'):
            # Reset pointer in case it was read by parser
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            file_name = getattr(file_obj, 'name', f"import_batch_{batch.id}.csv")
            batch.raw_file.save(file_name, ContentFile(file_obj.read()), save=False)
            batch.save()

        # Why: Create a traceable ImportAnomaly entry for each detected issue
        for anomaly in all_anomalies:
            ImportAnomaly.objects.create(
                import_batch=batch,
                row_reference=anomaly['row_reference'],
                anomaly_type=anomaly['anomaly_type'],
                description=anomaly['description'],
                raw_row_data=anomaly['raw_row_data'],
                suggested_action=anomaly['suggested_action'],
                status='PENDING'
            )

    return batch
