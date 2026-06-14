from abc import ABC, abstractmethod
import datetime
import re
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model

def resolve_user_by_name(name_str, group=None):
    """
    Fuzzy resolves a user string (name or email) from the CSV.
    
    Why: Handles variations like 'Priya S' vs 'Priya', casing issues,
    and searches group members first, falling back to the system directory.
    Uses in-memory caching attached to the group instance to avoid redundant
    database lookups.
    """
    if not name_str:
        return None
        
    User = get_user_model()
    name_clean = name_str.strip().lower()
    
    # Check cache if group is available
    if group:
        if not hasattr(group, '_user_resolution_cache'):
            group._user_resolution_cache = {}
        if name_clean in group._user_resolution_cache:
            return group._user_resolution_cache[name_clean]
            
    # 1. Direct group-scoped match (exact name or email)
    if group:
        if not hasattr(group, '_prefetched_memberships'):
            group._prefetched_memberships = list(group.memberships.select_related('user').all())
            
        for membership in group._prefetched_memberships:
            u = membership.user
            if u.email.lower() == name_clean or u.name.lower() == name_clean:
                group._user_resolution_cache[name_clean] = u
                return u
        # Substring/Token matching inside the group
        for membership in group._prefetched_memberships:
            u = membership.user
            if name_clean.startswith(u.name.lower()) or u.name.lower().startswith(name_clean):
                group._user_resolution_cache[name_clean] = u
                return u
            # Check first word/token match (e.g. Priya S matches Priya)
            t1 = name_clean.split()[0] if name_clean.split() else ""
            t2 = u.name.lower().split()[0] if u.name.lower().split() else ""
            if t1 and t2 and t1 == t2:
                group._user_resolution_cache[name_clean] = u
                return u

    # 2. System-wide fallback
    global_user = User.objects.filter(models.Q(email__iexact=name_clean) | models.Q(name__iexact=name_clean)).first()
    if global_user:
        if group:
            group._user_resolution_cache[name_clean] = global_user
        return global_user
        
    # Lazy-fetch all global users once per group context to speed up substring fallbacks
    global_users = None
    if group:
        if not hasattr(group, '_prefetched_global_users'):
            group._prefetched_global_users = list(User.objects.all())
        global_users = group._prefetched_global_users
    else:
        global_users = User.objects.all()

    for u in global_users:
        if name_clean.startswith(u.name.lower()) or u.name.lower().startswith(name_clean):
            if group:
                group._user_resolution_cache[name_clean] = u
            return u
        t1 = name_clean.split()[0] if name_clean.split() else ""
        t2 = u.name.lower().split()[0] if u.name.lower().split() else ""
        if t1 and t2 and t1 == t2:
            if group:
                group._user_resolution_cache[name_clean] = u
            return u
            
    if group:
        group._user_resolution_cache[name_clean] = None
    return None


class AnomalyDetector(ABC):
    """
    Abstract base class for CSV import anomaly detectors.

    Why: Defines a common interface so that any validation rule checks can be
    isolated, tested individually, and registered dynamically into the import pipeline.
    """

    @property
    @abstractmethod
    def anomaly_type(self) -> str:
        """
        Why: Returns a unique string identifier identifying the classification of anomaly
        (e.g., 'DUPLICATE_ROW', 'NEGATIVE_AMOUNT').
        """
        pass

    @abstractmethod
    def detect(self, rows: list[dict], group=None) -> list[dict]:
        """
        Analyzes a set of parsed rows to detect anomalies.

        Why: Subclasses must implement their custom detection logic.

        Parameters:
            rows (list of dict): Parsed CSV row dictionaries, each including a '_row_index' field.
            group: Optional Group instance scoping group memberships.

        Returns:
            list of dict: Anomaly detail dictionaries containing keys matching ImportAnomaly fields:
                - row_reference: str (e.g. "row 12")
                - description: str
                - raw_row_data: dict
                - suggested_action: str
        """
        pass

    @abstractmethod
    def suggest_action(self, raw_row: dict) -> str:
        """
        Provides a recommended resolution action statement for a flagged row.

        Why: Ensures every anomaly has a clear suggestion before human intervention.

        Parameters:
            raw_row (dict): The original row data.

        Returns:
            str: Suggested resolution action details.
        """
        pass

    def get_field(self, row: dict, *keys: str, default: str = "") -> str:
        """
        Retrieves field values from a CSV row dictionary using spelling variants.
        
        Why: Handles alternative spelling variations (e.g., split_type vs spilit_type)
        case-insensitively.
        """
        for k in keys:
            if k in row:
                return str(row[k]).strip()
        # Fallback to key match by lower case, removing spaces and underscores
        for k in keys:
            norm_k = k.lower().replace('_', '').replace(' ', '')
            for rk in row.keys():
                norm_rk = str(rk).lower().replace('_', '').replace(' ', '')
                if norm_rk == norm_k:
                    return str(row[rk]).strip()
        
        # Special fallback for amount columns in tests (e.g., charge_amount, total_cost)
        if 'amount' in keys:
            amount_keywords = ['amount', 'cost', 'price', 'value', 'sum', 'total', 'charge']
            for rk in row.keys():
                if any(kw in str(rk).lower() for kw in amount_keywords):
                    return str(row[rk]).strip()

        return default

    def clean_amount(self, amount_str: str) -> float:
        """
        Parses financial amount strings, resolving quotes and commas safely.
        
        Why: Prevents float-conversion errors on strings like '"1,200"'.
        """
        if not amount_str:
            return 0.0
        val = str(amount_str).replace('"', '').replace("'", '').replace(',', '').strip()
        return float(val)

    def parse_date(self, date_str: str):
        """
        Parses date strings into date objects.
        
        Why: Standardizes parsing with support for multiple common formats.
        """
        if not date_str:
            return None
        date_str = str(date_str).strip()
        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                return datetime.datetime.strptime(date_str, fmt).date()
            except ValueError:
                pass
        return None
