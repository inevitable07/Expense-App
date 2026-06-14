import datetime
import re
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from expenses.models import Expense, ExpenseSplit
from settlements.models import Settlement
from core.models import FXRate
from .parser import parse_csv
from .detectors.base import resolve_user_by_name

User = get_user_model()

def clean_amount_val(amount_str: str) -> Decimal:
    """
    Cleans and parses numeric string values to Decimal.
    """
    if not amount_str:
        return Decimal('0.00')
    val = str(amount_str).replace('"', '').replace("'", '').replace(',', '').strip()
    return Decimal(val)

def extract_override_date(final_action):
    if not final_action:
        return None
    # 1. Search for YYYY-MM-DD
    m = re.search(r'\b(\d{4})[-/](\d{2})[-/](\d{2})\b', final_action)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # 2. Search for DD-MM-YYYY
    m = re.search(r'\b(\d{2})[-/](\d{2})[-/](\d{4})\b', final_action)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None

def extract_override_user(final_action, group):
    if not final_action:
        return None
    # Check email pattern first
    m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', final_action)
    if m:
        u = resolve_user_by_name(m.group(0), group)
        if u:
            return u
    # Token-based scanning
    for token in re.split(r'[\s,()]+', final_action):
        if len(token) > 2:
            u = resolve_user_by_name(token, group)
            if u:
                return u
    return None

def extract_override_currency(final_action):
    if not final_action:
        return None
    m = re.search(r'\b(INR|USD)\b', final_action.upper())
    if m:
        return m.group(1)
    return None

def extract_override_rate(final_action):
    if not final_action:
        return None
    # Look for patterns like "rate 83.5" or just a float number in context of fx/exchange
    m = re.search(r'\b(?:rate|fx|exchange|at)\s+(\d+(?:\.\d+)?)\b', final_action.lower())
    if m:
        return Decimal(m.group(1))
    # Fallback to any standalone float that looks like an exchange rate (e.g. 70-90)
    m = re.search(r'\b(8[0-9](?:\.\d+)?|7[0-9](?:\.\d+)?)\b', final_action)
    if m:
        return Decimal(m.group(1))
    return None

@transaction.atomic
def apply_import(import_batch):
    """
    Applies the resolved anomalies in the batch and creates the appropriate database records.

    Why: Crucial final phase of the pipeline. Never silently edits or skips records.
    Ensures that only APPROVED/MODIFIED rows are processed and full audit history is preserved.
    """
    # 1. Verification Rule: If ANY anomaly in the batch is still PENDING, fail immediately.
    pending_anomalies = import_batch.anomalies.filter(status='PENDING')
    if pending_anomalies.exists():
        raise ValidationError(
            f"Cannot apply import batch. There are {pending_anomalies.count()} pending anomalies that require review."
        )

    if not import_batch.raw_file:
        raise ValidationError("Import batch raw file is missing.")

    # 2. Parse CSV rows to apply them
    rows = parse_csv(import_batch.raw_file)
    group = import_batch.group

    # Group anomalies by row_reference
    row_anomalies = {}
    for anomaly in import_batch.anomalies.all():
        row_anomalies.setdefault(anomaly.row_reference, []).append(anomaly)

    records_created = {
        'expenses': 0,
        'splits': 0,
        'settlements': 0
    }

    # Track processed lines to avoid double-processing duplicates in the same CSV run
    processed_rows = set()

    for row in rows:
        row_idx = row['_row_index']
        row_ref = f"row {row_idx}"

        if row_ref in processed_rows:
            continue

        anomalies_for_row = row_anomalies.get(row_ref, [])

        # 3. Skip row if any anomaly associated with this row is REJECTED
        if any(anom.status == 'REJECTED' for anom in anomalies_for_row):
            continue

        # Get final action description override text (if modified)
        final_actions = " ".join([anom.final_action for anom in anomalies_for_row if anom.final_action])

        # Date Resolution
        date = extract_override_date(final_actions)
        if not date:
            csv_date_str = row.get('date', '').strip()
            # Try to parse standard dates
            for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    date = datetime.datetime.strptime(csv_date_str, fmt).date()
                    break
                except ValueError:
                    pass

        if not date:
            raise ValidationError(
                f"Invalid date format on row {row_idx} and no valid override date was provided in Meera's final action."
            )

        # Payer Resolution
        payer_user = extract_override_user(final_actions, group)
        if not payer_user:
            payer_name = row.get('paid_by') or row.get('payer', '')
            payer_user = resolve_user_by_name(payer_name, group)

        if not payer_user:
            raise ValidationError(
                f"Could not resolve payer '{row.get('paid_by')}' on row {row_idx} into a registered user."
            )

        # Amount Resolution
        amount = clean_amount_val(row.get('amount', '0.00'))

        # Currency Resolution
        currency = extract_override_currency(final_actions)
        if not currency:
            currency = row.get('currency', '').strip().upper()
        if not currency:
            raise ValidationError(f"Missing currency on row {row_idx} and no override was provided.")

        # Classify as Expense or Settlement
        is_settlement = False
        desc_lower = row.get('description', '').lower()
        notes_lower = row.get('notes', '').lower()
        settlement_keywords = ['settled', 'settlement', 'paid back', 'reimbursement', 'returned money']

        # If has a settlement misclassification anomaly that was approved/modified, OR contains settlement text and split_type is empty
        has_settlement_anomaly = any(anom.anomaly_type == 'SETTLEMENT_MISCLASSIFICATION' for anom in anomalies_for_row)
        split_type_val = row.get('split_type') or row.get('spilit_type') or ''

        if has_settlement_anomaly or (any(kw in desc_lower for kw in settlement_keywords) and not split_type_val):
            is_settlement = True

        if is_settlement:
            # Create Settlement record
            split_with_str = row.get('split_with') or row.get('spilit_with') or ''
            paid_to_user = extract_override_user(final_actions, group)
            if not paid_to_user and split_with_str:
                first_name = split_with_str.split(';')[0].strip()
                paid_to_user = resolve_user_by_name(first_name, group)

            if not paid_to_user:
                raise ValidationError(f"Could not resolve recipient user for settlement on row {row_idx}.")

            # Settlements require positive amount_inr
            amount_inr = abs(amount)

            # If USD, we might need conversion rate? Let's check FX rate
            if currency == 'USD':
                fx_rate = FXRate.objects.filter(from_currency='USD', to_currency='INR', effective_date=date).first()
                if not fx_rate:
                    rate_val = extract_override_rate(final_actions)
                    if rate_val:
                        fx_rate = FXRate.objects.create(
                            from_currency='USD',
                            to_currency='INR',
                            rate=rate_val,
                            effective_date=date
                        )
                if fx_rate:
                    amount_inr = (amount_inr * fx_rate.rate).quantize(Decimal('0.01'))
                else:
                    raise ValidationError(f"FXRate for USD to INR on {date} is missing for settlement on row {row_idx}.")

            Settlement.objects.create(
                group=group,
                paid_by=payer_user,
                paid_to=paid_to_user,
                amount_inr=amount_inr,
                date=date,
                note=row.get('description', '') + (" - " + row.get('notes', '') if row.get('notes') else "")
            )
            records_created['settlements'] += 1

        else:
            # Create Expense record
            stype = row.get('split_type') or row.get('spilit_type') or 'EQUAL'
            stype_mapped = stype.strip().upper()
            if stype_mapped == 'SHARE':
                stype_mapped = 'SHARES'
            if stype_mapped not in ['EQUAL', 'EXACT', 'PERCENTAGE', 'SHARES']:
                stype_mapped = 'EQUAL'

            # Parse split participants
            split_with_str = row.get('split_with') or row.get('spilit_with') or ''
            members = []
            if split_with_str:
                for name in split_with_str.split(';'):
                    name = name.strip()
                    if name:
                        u = resolve_user_by_name(name, group)
                        if u:
                            members.append(u)

            if not members:
                # Default to all current active memberships
                members = [mem.user for mem in group.memberships.all()]

            # Parse split details input
            split_details_str = row.get('split_details') or row.get('spilit_details') or ''
            split_input = {}
            if split_details_str:
                for part in split_details_str.split(';'):
                    part = part.strip()
                    if part:
                        tokens = part.rsplit(None, 1)
                        if len(tokens) == 2:
                            name, val_str = tokens[0].strip(), tokens[1].strip()
                            u = resolve_user_by_name(name, group)
                            if u:
                                val_clean = val_str.replace('%', '').replace('INR', '').replace('USD', '').strip()
                                split_input[u] = Decimal(val_clean)

            # FX rate resolution for USD Expenses
            fx_rate = None
            if currency == 'USD':
                fx_rate = FXRate.objects.filter(from_currency='USD', to_currency='INR', effective_date=date).first()
                if not fx_rate:
                    rate_val = extract_override_rate(final_actions)
                    if rate_val:
                        fx_rate = FXRate.objects.create(
                            from_currency='USD',
                            to_currency='INR',
                            rate=rate_val,
                            effective_date=date
                        )
                if not fx_rate:
                    raise ValidationError(
                        f"FXRate for USD to INR on {date} is missing and no rate override was provided for row {row_idx}."
                    )

            expense = Expense(
                group=group,
                paid_by=payer_user,
                description=row.get('description', ''),
                date=date,
                original_amount=amount,
                original_currency=currency,
                fx_rate_used=fx_rate,
                split_type=stype_mapped,
                source='IMPORTED',
                import_batch=import_batch
            )
            # clean calculates amount_inr and validates FX rates
            expense.full_clean()
            expense.save()
            records_created['expenses'] += 1

            # Compute and create Splits
            from expenses.services import compute_splits
            splits_map = compute_splits(expense, split_input, members)
            for user_id, share_amt in splits_map.items():
                ExpenseSplit.objects.create(
                    expense=expense,
                    user_id=user_id,
                    share_amount_inr=share_amt
                )
                records_created['splits'] += 1

        processed_rows.add(row_ref)

    # 4. Update batch status when complete
    import_batch.status = 'APPROVED'
    import_batch.save()

    return records_created
