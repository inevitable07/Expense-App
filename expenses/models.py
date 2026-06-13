from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

# =====================================================================
# SECTION 1: MODEL DEFINITIONS
# =====================================================================

class Expense(models.Model):
    """
    Represents an expense record incurred in a group.
    
    Why: Records financial transactions, who paid, original amount,
    and base currency mapping for split computations.
    
    Currency Conversion Policy:
    - Base currency for ledger calculations is INR.
    - If original_currency is INR, amount_inr equals original_amount.
    - If original_currency is USD, an FXRate record must be associated
      and amount_inr is computed as (original_amount * fx_rate_used.rate),
      rounded to 2 decimal places using ROUND_HALF_UP at the database save boundary.
    """
    
    # Why: Links the expense to a specific sharing group.
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.CASCADE,
        related_name='expenses',
        verbose_name="Group",
        help_text="The group this expense belongs to."
    )
    
    # Why: Links the expense to the user who paid for it.
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='expenses_paid',
        verbose_name="Paid By",
        help_text="The user who paid the total amount."
    )
    
    # Why: Clear explanation of what the expense represents.
    description = models.CharField(
        max_length=255,
        verbose_name="Description",
        help_text="Description of the expense (e.g. Dinner, Cab fare)."
    )
    
    # Why: Date when the transaction occurred. Determines scoping and valid exchange rates.
    date = models.DateField(
        verbose_name="Date",
        help_text="The date when the expense occurred."
    )
    
    # Why: Stores original input value. We use 12 digits, 2 decimal places for financial safety.
    original_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Original Amount",
        help_text="The total amount of the transaction in the original currency."
    )
    
    # Why: Captures whether the transaction occurred in INR or USD.
    original_currency = models.CharField(
        max_length=3,
        choices=[('INR', 'Indian Rupee'), ('USD', 'US Dollar')],
        verbose_name="Original Currency",
        help_text="The currency in which the expense was originally paid."
    )
    
    # Why: Calculated base value in INR. All balance ledger operations run on this field.
    # marked blank=True so Django field-clean validators don't raise errors before clean() computes it.
    amount_inr = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        verbose_name="Amount in INR",
        help_text="The converted transaction value in base currency (INR)."
    )
    
    # Why: Links to conversion rate data when transaction occurred in USD. Null for INR.
    fx_rate_used = models.ForeignKey(
        'core.FXRate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="FX Rate Used",
        help_text="Exchange rate reference. Required if currency is not INR."
    )
    
    # Why: Tracks the strategy selected to distribute this expense among members.
    split_type = models.CharField(
        max_length=15,
        choices=[
            ('EQUAL', 'Equal'),
            ('EXACT', 'Exact'),
            ('PERCENTAGE', 'Percentage'),
            ('SHARES', 'Shares')
        ],
        verbose_name="Split Type",
        help_text="The formula used to distribute shares."
    )
    
    # Why: Allows soft-voiding or replacing expenses without physical deletion.
    status = models.CharField(
        max_length=15,
        choices=[
            ('ACTIVE', 'Active'),
            ('VOID', 'Void'),
            ('SUPERSEDED', 'Superseded')
        ],
        default='ACTIVE',
        verbose_name="Status",
        help_text="The current state of the expense."
    )
    
    # Why: Audit trail flag to trace if manual entry or batch file upload.
    source = models.CharField(
        max_length=15,
        choices=[
            ('MANUAL', 'Manual'),
            ('IMPORTED', 'Imported')
        ],
        default='MANUAL',
        verbose_name="Source",
        help_text="Where the entry originated."
    )
    
    # Why: Traceability link to tracking upload batch in the imports app.
    import_batch = models.ForeignKey(
        'imports.ImportBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Import Batch",
        help_text="Reference to import metadata batch. Null if MANUAL."
    )

    def clean(self):
        """
        Why: Enforces that USD transactions specify an FXRate converting USD to INR,
        and executes the conversion formula.
        """
        super().clean()
        
        if self.original_currency != 'INR':
            if not self.fx_rate_used:
                raise ValidationError({
                    'fx_rate_used': "An FX rate must be specified for non-INR expenses."
                })
            
            # Why: Ensures the FX rate matches from_currency and to_currency configurations.
            if self.fx_rate_used.from_currency != self.original_currency or self.fx_rate_used.to_currency != 'INR':
                raise ValidationError({
                    'fx_rate_used': f"The selected FX rate must convert from {self.original_currency} to INR."
                })
            
            # Why: Computes converted amount and rounds only at this database persistence boundary.
            raw_converted = self.original_amount * self.fx_rate_used.rate
            self.amount_inr = raw_converted.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            # Why: In base currency, conversion rate is implicitly 1.0, so no fx_rate_used is required.
            self.amount_inr = self.original_amount

    def save(self, *args, **kwargs):
        """
        Why: Forces validation clean checks to run before saving to ensure data consistency.
        """
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        """
        Why: Returns string representation of Expense detailing description and amount.
        """
        return f"{self.description} ({self.amount_inr} INR) on {self.date}"


class ExpenseSplit(models.Model):
    """
    Represents the calculated portion of an expense allocated to a user.
    
    Why: Records the ledger breakdown specifying who owes what for each expense.
    """
    
    # Why: Links the split back to the parent expense.
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name='splits',
        verbose_name="Expense",
        help_text="The parent expense."
    )
    
    # Why: Links the split share to a specific user.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='expense_splits',
        verbose_name="User",
        help_text="The user responsible for this split share."
    )
    
    # Why: The precise debt share calculated in INR.
    share_amount_inr = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Share Amount in INR",
        help_text="The user's calculated share in base currency (INR)."
    )

    def __str__(self):
        """
        Why: Returns string representation detailing user debt share.
        """
        return f"{self.user.email} owes {self.share_amount_inr} INR for {self.expense.description}"
