from .base import AnomalyDetector

class InvalidSplitDetector(AnomalyDetector):
    """
    Validates that the split details configuration is mathematically consistent.

    Why: Sum of percentage splits must equal 100%, exact splits must sum to the total amount,
    and shares must be positive. Otherwise, the ledger will be unbalanced.

    False-Positive Risks:
        Small floating-point precision mismatches could be flagged if input is formatted poorly.
    """

    @property
    def anomaly_type(self) -> str:
        return 'INVALID_SPLIT'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []

        for row in rows:
            stype = self.get_field(row, 'split_type', 'spilit_type').lower()
            amt_str = self.get_field(row, 'amount')
            details_str = self.get_field(row, 'split_details', 'spilit_details')

            try:
                amount = self.clean_amount(amt_str)
            except ValueError:
                continue  # Missing or invalid amount handled by other detectors

            if not stype:
                continue

            if stype == 'exact':
                if not details_str:
                    anomalies.append({
                        'row_reference': f"row {row['_row_index']}",
                        'description': "Exact split type requires split details.",
                        'raw_row_data': row,
                        'suggested_action': self.suggest_action(row)
                    })
                else:
                    total = 0.0
                    for part in details_str.split(';'):
                        part = part.strip()
                        if part:
                            tokens = part.rsplit(None, 1)
                            if len(tokens) == 2:
                                try:
                                    val = float(tokens[1].replace('INR', '').replace('USD', '').strip())
                                    total += val
                                except ValueError:
                                    pass
                    if abs(total - amount) > 0.01:
                        anomalies.append({
                            'row_reference': f"row {row['_row_index']}",
                            'description': f"Sum of exact splits ({total}) does not equal total amount ({amount}).",
                            'raw_row_data': row,
                            'suggested_action': self.suggest_action(row)
                        })

            elif stype == 'percentage':
                if not details_str:
                    anomalies.append({
                        'row_reference': f"row {row['_row_index']}",
                        'description': "Percentage split type requires split details.",
                        'raw_row_data': row,
                        'suggested_action': self.suggest_action(row)
                    })
                else:
                    total = 0.0
                    for part in details_str.split(';'):
                        part = part.strip()
                        if part:
                            tokens = part.rsplit(None, 1)
                            if len(tokens) == 2:
                                try:
                                    val = float(tokens[1].replace('%', '').strip())
                                    total += val
                                except ValueError:
                                    pass
                    if abs(total - 100.0) > 0.01:
                        anomalies.append({
                            'row_reference': f"row {row['_row_index']}",
                            'description': f"Sum of percentages ({total}%) does not equal 100%.",
                            'raw_row_data': row,
                            'suggested_action': self.suggest_action(row)
                        })

            elif stype == 'shares':
                if details_str:
                    for part in details_str.split(';'):
                        part = part.strip()
                        if part:
                            tokens = part.rsplit(None, 1)
                            if len(tokens) == 2:
                                try:
                                    val = float(tokens[1].strip())
                                    if val < 0:
                                        anomalies.append({
                                            'row_reference': f"row {row['_row_index']}",
                                            'description': f"Negative share count ({val}) is invalid.",
                                            'raw_row_data': row,
                                            'suggested_action': self.suggest_action(row)
                                        })
                                        break
                                except ValueError:
                                    pass

        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Require correction of split configurations before import."
