from .base import AnomalyDetector

class UnsupportedCurrencyDetector(AnomalyDetector):
    """
    Scans for unsupported currencies in CSV entries.

    Why: The system only supports INR and USD ledgers. Any other currency requires
    explicit exchange rate configuration and mapping.

    False-Positive Risks:
        Valid international currencies like EUR or GBP will be flagged because they are unsupported.
    """

    @property
    def anomaly_type(self) -> str:
        return 'UNSUPPORTED_CURRENCY'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        supported = {'INR', 'USD'}
        for row in rows:
            currency = self.get_field(row, 'currency').strip().upper()
            if currency and currency not in supported:
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': f"Currency '{currency}' is not supported by the system (Supported: INR, USD).",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row)
                })
        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Require manual review and currency mapping."
