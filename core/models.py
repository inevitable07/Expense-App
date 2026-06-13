from django.db import models

class FXRate(models.Model):
    """
    Represents a foreign exchange rate between two currencies for a specific date.
    
    Why: Resolves foreign currency payments into the base accounting currency (INR)
    with auditable conversion rates on the date the transaction occurred.
    """
    
    # Why: The source currency code (e.g., USD). Max 3 characters for ISO 4217 currency codes.
    from_currency = models.CharField(
        max_length=3,
        verbose_name="From Currency",
        help_text="The source currency code (e.g., USD)."
    )
    
    # Why: The destination currency code (e.g., INR). Max 3 characters for ISO 4217 currency codes.
    to_currency = models.CharField(
        max_length=3,
        verbose_name="To Currency",
        help_text="The target currency code (e.g., INR)."
    )
    
    # Why: Decimal value representing the exchange multiplier.
    # We use 12 digits and 6 decimal places to ensure high precision during conversion.
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name="Exchange Rate",
        help_text="The conversion multiplier. Stored with 6 decimal places for precision."
    )
    
    # Why: Currency rates fluctuate daily. This marks the day for which this rate applies.
    effective_date = models.DateField(
        verbose_name="Effective Date",
        help_text="The date for which this exchange rate is valid."
    )

    class Meta:
        # Why: Prevents conflicting rates for the same conversion on the same date.
        unique_together = ('from_currency', 'to_currency', 'effective_date')

    def __str__(self):
        """
        Why: Returns string representation detailing rate conversion on the date.
        """
        return f"{self.from_currency} to {self.to_currency} = {self.rate} on {self.effective_date}"
