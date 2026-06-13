from datetime import date
from django.db import models
from django.core.exceptions import ValidationError
from .models import GroupMembership

def is_member_active_on_date(user, group, check_date):
    """
    Helper function to determine if a user was an active member of a group on a specific date.
    
    Future modules MUST use this helper instead of duplicating logic.
    
    Why: Centralizes membership query logic so that other business units
    (like expenses splitting, balance calculation, and settlements) can reliably
    determine eligibility without duplicating SQL checks.
    
    Validation:
    - check_date must be a date object (or datetime.date).
    
    Logic:
    - User is considered an active member on check_date if:
      joined_at <= check_date AND (left_at IS NULL OR left_at >= check_date)
    """
    # Why: Ensures date input is of correct type to prevent silent database query mismatches.
    if not isinstance(check_date, date):
        raise ValidationError("The check_date must be a datetime.date instance.")
        
    return GroupMembership.objects.filter(
        user=user,
        group=group,
        joined_at__lte=check_date
    ).filter(
        models.Q(left_at__isnull=True) | models.Q(left_at__gte=check_date)
    ).exists()
