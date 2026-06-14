import re
from django.contrib.auth import get_user_model
from expenses.models import Expense
from settlements.models import Settlement
from .parser import parse_csv

def generate_import_report(import_batch) -> dict:
    """
    Generates a structured dictionary report representing the import batch audit trail.

    Why: Keeps a complete lineage audit log showing original CSV row references,
    detected anomalies, actions taken, and the exact database records created or skipped.
    """
    anomalies = import_batch.anomalies.all().order_by('row_reference')
    expenses = list(Expense.objects.filter(import_batch=import_batch).prefetch_related('splits__user'))
    
    # Trace Settlements by their identifying note prefix
    settlements = list(Settlement.objects.filter(
        group=import_batch.group, 
        note__startswith=f"Import Batch #{import_batch.id} -"
    ))

    # Parse CSV to trace skipped rows
    rows = []
    if import_batch.raw_file:
        try:
            rows = parse_csv(import_batch.raw_file)
        except Exception:
            pass

    # Group anomalies by row index
    row_anomalies = {}
    for anomaly in anomalies:
        # Extract numeric row number from "row X"
        m = re.search(r'\d+', anomaly.row_reference)
        idx = int(m.group(0)) if m else None
        if idx is not None:
            row_anomalies.setdefault(idx, []).append(anomaly)

    # Compile skipped vs applied rows
    skipped_rows = []
    applied_rows = []
    
    for row in rows:

        idx = row['_row_index']
        anoms = row_anomalies.get(idx, [])
        is_rejected = any(anom.status == 'REJECTED' for anom in anoms)
        
        row_summary = {
            'row_index': idx,
            'description': row.get('description', ''),
            'paid_by': row.get('paid_by') or row.get('payer', ''),
            'amount': row.get('amount', ''),
            'currency': row.get('currency', ''),
            'anomalies': [
                {
                    'anomaly_type': anom.anomaly_type,
                    'description': anom.description,
                    'status': anom.status,
                    'suggested_action': anom.suggested_action,
                    'final_action': anom.final_action or "None"
                } for anom in anoms
            ]
        }
        
        if is_rejected:
            skipped_rows.append(row_summary)
        else:
            applied_rows.append(row_summary)

    # Determine approval history metadata
    approval_history = []
    for anomaly in anomalies:
        approval_history.append({
            'row_reference': anomaly.row_reference,
            'anomaly_type': anomaly.anomaly_type,
            'status': anomaly.status,
            'final_action': anomaly.final_action or "Approved as-is"
        })

    return {
        'batch_id': import_batch.id,
        'group_name': import_batch.group.name if import_batch.group else 'Unknown',
        'uploaded_by': import_batch.uploaded_by.email if import_batch.uploaded_by else 'System',
        'uploaded_at': import_batch.uploaded_at,
        'status': import_batch.status,
        'anomalies_count': anomalies.count(),
        'expenses_created_count': len(expenses),
        'settlements_created_count': len(settlements),
        'skipped_rows_count': len(skipped_rows),
        'expenses': expenses,
        'settlements': settlements,
        'skipped_rows': skipped_rows,
        'applied_rows': applied_rows,
        'approval_history': approval_history
    }
