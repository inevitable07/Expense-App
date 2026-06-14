from .base import AnomalyDetector

class MissingRequiredFieldsDetector(AnomalyDetector):
    """
    Checks for the presence of mandatory CSV fields.

    Why: Expenses cannot be imported without dates, descriptions, amounts, or payers.

    False-Positive Risks:
        None.
    """

    @property
    def anomaly_type(self) -> str:
        return 'MISSING_REQUIRED_FIELDS'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []

        for row in rows:
            missing = []

            if not self.get_field(row, 'amount'):
                missing.append('amount')
            if not self.get_field(row, 'date'):
                missing.append('date')
            if not self.get_field(row, 'description'):
                missing.append('description')
            if not self.get_field(row, 'paid_by', 'paidby', 'payer'):
                missing.append('paid_by')

            # Split information check: split_with or split_type
            if not self.get_field(row, 'split_with', 'spilit_with') and not self.get_field(row, 'split_type', 'spilit_type'):
                missing.append('split information')

            if missing:
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': f"Missing required fields: {', '.join(missing)}.",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row)
                })

        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Require user correction before import."
