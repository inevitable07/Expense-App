from .base import AnomalyDetector

class SettlementMisclassificationDetector(AnomalyDetector):
    """
    Flags rows that appear to be direct debt settlements logged as expenses.

    Why: Debt repayments should be logged as Settlements, not new Expenses,
    to avoid doubling total group spending metrics.

    False-Positive Risks:
        A purchase description that contains words like 'settlement' (e.g., 'Settlement Café lunch')
        could be flagged.
    """

    @property
    def anomaly_type(self) -> str:
        return 'SETTLEMENT_MISCLASSIFICATION'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        keywords = ['settled', 'settlement', 'paid back', 'reimbursement', 'returned money']
        for row in rows:
            desc = self.get_field(row, 'description').lower()
            notes = self.get_field(row, 'notes', 'note').lower()

            import re
            is_settle = any(kw in desc for kw in keywords) or any(kw in notes for kw in keywords)
            if not is_settle:
                # Matches patterns like "paid Aisha back", "paid back", "paid Rohan back"
                if re.search(r'\bpaid\b.*\bback\b', desc) or re.search(r'\bpaid\b.*\bback\b', notes):
                    is_settle = True

            if is_settle:
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': "Description or notes indicate this transaction is a debt settlement/reimbursement.",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row)
                })

        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Suggest conversion into Settlement model. Require approval."
