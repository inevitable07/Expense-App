from .base import AnomalyDetector

class MissingPayerDetector(AnomalyDetector):
    """
    Flags rows where the payer (paid_by) is empty or missing.

    Why: Every expense must have an associated payer to balance credits and debits.

    False-Positive Risks:
        None. Payer is a required field for ledger consistency.
    """

    @property
    def anomaly_type(self) -> str:
        return 'MISSING_PAYER'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        for row in rows:
            paid_by = self.get_field(row, 'paid_by', 'paidby', 'payer')
            if not paid_by:
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': "Payer field ('paid_by') is empty, NULL, or missing.",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row)
                })
        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Do not assign a payer automatically. Require user selection."
