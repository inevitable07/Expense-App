from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

User = get_user_model()

# =====================================================================
# SECTION 2: EQUAL SPLIT LOGIC
# =====================================================================

def _compute_equal_split(amount_inr, payer_id, member_ids):
    """
    Computes equal split shares.
    
    Why: Handles distribution where the amount is divided equally among members.
    Rounding Policy:
    - Base share is computed by dividing total amount by the number of members
      and rounding down to the nearest cent (Decimal('0.01')).
    - Payer absorbs any fractional remainder cents (amount_inr - sum(base shares))
      so that the sum of split details is exactly equal to the total expense value.
    """
    N = len(member_ids)
    if N == 0:
        raise ValidationError("Equal split requires at least one member.")

    # Calculate base share per user, rounded down to nearest cent
    base_share = (amount_inr / Decimal(N)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    # Map shares
    shares = {m_id: base_share for m_id in member_ids}
    
    # Calculate remainder cents
    allocated_sum = sum(shares.values())
    remainder = amount_inr - allocated_sum
    
    # Assign remainder to the payer
    if remainder != 0:
        if payer_id in shares:
            shares[payer_id] += remainder
        else:
            shares[payer_id] = remainder
            
    return shares


# =====================================================================
# SECTION 3: EXACT/PERCENTAGE/SHARES SPLIT LOGIC
# =====================================================================

def _compute_exact_split(amount_inr, normalized_input, member_ids):
    """
    Validates and maps exact split shares.
    
    Why: Handles splits where users specify exact monetary amounts.
    Validation:
    - Input keys must correspond to the group members in this split.
    - The sum of exact shares must equal the total amount_inr.
    """
    # Verify input keys match member ids
    input_keys = set(normalized_input.keys())
    member_keys = set(member_ids)
    
    if not input_keys.issubset(member_keys):
        raise ValidationError("Exact split contains users who are not members of the split group.")
        
    total_input = sum(normalized_input.values())
    if total_input != amount_inr:
        raise ValidationError(
            f"The sum of exact shares ({total_input} INR) does not match the total expense amount ({amount_inr} INR)."
        )
        
    # Build complete dict (defaulting missing members to 0)
    shares = {m_id: Decimal('0.00') for m_id in member_ids}
    shares.update(normalized_input)
    return shares

def _compute_percentage_split(amount_inr, payer_id, normalized_input, member_ids):
    """
    Computes percentage split shares.
    
    Why: Handles splits where shares are specified as percentages of the total.
    Rounding Policy:
    - Base share is computed as (amount_inr * percentage / 100), rounded to the
      nearest cent using ROUND_HALF_UP.
    - Payer absorbs any remainder cents (amount_inr - sum(base shares)) to guarantee
      precise total coverage.
    """
    input_keys = set(normalized_input.keys())
    member_keys = set(member_ids)
    
    if not input_keys.issubset(member_keys):
        raise ValidationError("Percentage split contains users who are not members of the split group.")
        
    total_percentage = sum(normalized_input.values())
    if total_percentage != Decimal('100.00') and total_percentage != 100:
        raise ValidationError(
            f"The sum of percentages must equal 100%. Got {total_percentage}%."
        )

    shares = {}
    for m_id in member_ids:
        pct = normalized_input.get(m_id, Decimal('0.00'))
        share = (amount_inr * (pct / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        shares[m_id] = share

    # Allocate remainder cents to payer
    allocated_sum = sum(shares.values())
    remainder = amount_inr - allocated_sum
    if remainder != 0:
        if payer_id in shares:
            shares[payer_id] += remainder
        else:
            shares[payer_id] = remainder

    return shares

def _compute_shares_split(amount_inr, payer_id, normalized_input, member_ids):
    """
    Computes proportional split shares.
    
    Why: Handles splits where shares are specified as relative counts (e.g. 2 shares, 1 share).
    Rounding Policy:
    - Base share is computed proportionally and rounded down to the nearest cent.
    - Payer absorbs any remainder cents to guarantee precise total coverage.
    """
    input_keys = set(normalized_input.keys())
    member_keys = set(member_ids)
    
    if not input_keys.issubset(member_keys):
        raise ValidationError("Shares split contains users who are not members of the split group.")
        
    total_shares = sum(normalized_input.values())
    if total_shares <= 0:
        raise ValidationError("Total shares count must be greater than zero.")

    shares = {}
    for m_id in member_ids:
        share_count = normalized_input.get(m_id, Decimal('0.00'))
        if share_count < 0:
            raise ValidationError("Individual share counts cannot be negative.")
        share = (amount_inr * (share_count / total_shares)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        shares[m_id] = share

    # Allocate remainder cents to payer
    allocated_sum = sum(shares.values())
    remainder = amount_inr - allocated_sum
    if remainder != 0:
        if payer_id in shares:
            shares[payer_id] += remainder
        else:
            shares[payer_id] = remainder

    return shares


# =====================================================================
# SECTION 4: CURRENCY CONVERSION LOGIC
# =====================================================================

def compute_splits(expense, split_input, members):
    """
    Main split engine entry point.
    
    Why: Orchestrates the validation, normalization of inputs, and execution of
    the selected split strategy.
    
    Input Normalization:
    - normalizes all member list and split_input keys to integer user IDs.
    
    Returns:
    - dict of {user_id: share_amount_inr_decimal}
    """
    # 1. Normalize member IDs
    member_ids = []
    for m in members:
        m_id = m.id if hasattr(m, 'id') else int(m)
        member_ids.append(m_id)
        
    # Remove duplicate member IDs if any
    member_ids = list(set(member_ids))
    
    # 2. Normalize payer ID
    payer_id = expense.paid_by.id if hasattr(expense.paid_by, 'id') else int(expense.paid_by)
    
    # 3. Normalize split_input keys to user ID integers and values to Decimal
    normalized_input = {}
    if split_input:
        for k, v in split_input.items():
            u_id = k.id if hasattr(k, 'id') else int(k)
            normalized_input[u_id] = Decimal(str(v))

    # 4. Dispatch to selected split strategy
    stype = expense.split_type
    
    if stype == 'EQUAL':
        return _compute_equal_split(expense.amount_inr, payer_id, member_ids)
    elif stype == 'EXACT':
        return _compute_exact_split(expense.amount_inr, normalized_input, member_ids)
    elif stype == 'PERCENTAGE':
        return _compute_percentage_split(expense.amount_inr, payer_id, normalized_input, member_ids)
    elif stype == 'SHARES':
        return _compute_shares_split(expense.amount_inr, payer_id, normalized_input, member_ids)
    else:
        raise ValidationError(f"Unsupported split type: {stype}")
