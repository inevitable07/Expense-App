from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

class Settlement(models.Model):
    """
    Represents a direct payment from one group member to another to settle debts.

    Why: Allows members to settle balances directly. Settlements are tracked
    separately from expenses because they do not represent new spending, but
    rather a transfer of funds to resolve existing debts.
    """

    # Why: Links the settlement to a specific expense sharing group.
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.CASCADE,
        related_name='settlements',
        verbose_name="Group",
        help_text="The group this settlement belongs to."
    )

    # Why: Links the settlement to the member who made the payment (debtor).
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='settlements_paid',
        verbose_name="Paid By",
        help_text="The user who paid the settlement amount."
    )

    # Why: Links the settlement to the member who received the payment (creditor).
    paid_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='settlements_received',
        verbose_name="Paid To",
        help_text="The user who received the settlement amount."
    )

    # Why: Captures the amount paid in the base currency (INR). We use 12 digits,
    # 2 decimal places for financial safety.
    amount_inr = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Amount in INR",
        help_text="The settlement payment amount in INR."
    )

    # Why: The date when the payment was made.
    date = models.DateField(
        verbose_name="Date",
        help_text="The date when the settlement payment was made."
    )

    # Why: Optional description or note for the settlement (e.g. UPI transaction ID).
    note = models.TextField(
        blank=True,
        default="",
        verbose_name="Note",
        help_text="Optional description or note regarding the payment (e.g., transaction reference)."
    )

    def clean(self):
        """
        Why: Enforces business logic rules:
        1. Settlement amount must be positive.
        2. A user cannot pay a settlement to themselves.
        """
        super().clean()

        if self.amount_inr is not None and self.amount_inr <= Decimal('0.00'):
            raise ValidationError({
                'amount_inr': "Settlement amount must be greater than zero."
            })

        if self.paid_by_id and self.paid_to_id and self.paid_by == self.paid_to:
            raise ValidationError({
                'paid_to': "A user cannot pay a settlement to themselves."
            })

    def save(self, *args, **kwargs):
        """
        Why: Ensures model validations are checked before writing to the database.
        """
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        """
        Why: Returns human-readable representation of the settlement payment.
        """
        return f"{self.paid_by.name} paid {self.amount_inr} INR to {self.paid_to.name} on {self.date}"
