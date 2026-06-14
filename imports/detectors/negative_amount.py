from .base import AnomalyDetector

class NegativeAmountDetector(AnomalyDetector):
    """
    Scans for negative amounts in the CSV rows.

    Why: Expenses are generally positive values. A negative amount usually represents
    a refund transaction that needs to be distributed back to the participants.

    False-Positive Risks:
        Valid corrections, discounts, or refunds recorded as expenses could be flagged.
    """

    @property
    def anomaly_type(self) -> str:
        return 'NEGATIVE_AMOUNT'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        for row in rows:
            amt_str = self.get_field(row, 'amount')
            if not amt_str:
                continue
            try:
                amt = self.clean_amount(amt_str)
                if amt < 0:
                    anomalies.append({
                        'row_reference': f"row {row['_row_index']}",
                        'description': f"Negative quantity '{amt_str}' found in amount column.",
                        'raw_row_data': row,
                        'suggested_action': self.suggest_action(row)
                    })
            except ValueError:
                pass
        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Treat as refund transaction. If refund distribution cannot be determined confidently, require manual review."
