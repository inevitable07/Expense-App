from .base import AnomalyDetector

class ZeroAmountDetector(AnomalyDetector):
    """
    Flags rows with an expense amount of zero.

    Why: Valid expense transactions should have non-zero financial values. A zero amount
    is suspicious and could represent a placeholder or system logging issue.

    False-Positive Risks:
        Legitimate zero-cost informational logs could be flagged.
    """

    @property
    def anomaly_type(self) -> str:
        return 'ZERO_AMOUNT'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        for row in rows:
            amt_str = self.get_field(row, 'amount')
            if not amt_str:
                continue
            try:
                amt = self.clean_amount(amt_str)
                if amt == 0:
                    anomalies.append({
                        'row_reference': f"row {row['_row_index']}",
                        'description': "Expense amount is zero.",
                        'raw_row_data': row,
                        'suggested_action': self.suggest_action(row)
                    })
            except ValueError:
                pass
        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Flag for review. Recommend ignoring the row unless user explicitly approves import."
