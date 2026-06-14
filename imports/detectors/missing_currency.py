from .base import AnomalyDetector

class MissingCurrencyDetector(AnomalyDetector):
    """
    Scans for rows with missing currency information.

    Why: The system supports multiple currencies (INR, USD). Missing currency leads to
    ambiguity because the system cannot assume a default.

    False-Positive Risks:
        None. Currency must be explicitly provided for financial accuracy.
    """

    @property
    def anomaly_type(self) -> str:
        return 'MISSING_CURRENCY'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        for row in rows:
            currency = self.get_field(row, 'currency')
            if not currency:
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': "Currency field is empty, NULL, or missing.",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row)
                })
        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Do not assume INR or USD. Require user review and currency selection."
