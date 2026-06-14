from .base import AnomalyDetector

class SplitTypeMismatchDetector(AnomalyDetector):
    """
    Checks if the declared split_type matches the details allocation format.

    Why: Helps ensure data input matches logical schemas before creating database splits.

    False-Positive Risks:
        Cases where details are given for documentation but logical equal splits are desired.
    """

    @property
    def anomaly_type(self) -> str:
        return 'SPLIT_TYPE_MISMATCH'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []

        for row in rows:
            stype = self.get_field(row, 'split_type', 'spilit_type').strip().lower()
            details = self.get_field(row, 'split_details', 'spilit_details').strip()

            if not stype or not details:
                continue

            if stype == 'equal':
                # Check if the split details contain unequal shares
                vals = []
                for part in details.split(';'):
                    part = part.strip()
                    if part:
                        tokens = part.rsplit(None, 1)
                        if len(tokens) == 2:
                            try:
                                vals.append(float(tokens[1].replace('%', '').strip()))
                            except ValueError:
                                pass
                if len(set(vals)) > 1:
                    anomalies.append({
                        'row_reference': f"row {row['_row_index']}",
                        'description': "Declared split_type is 'equal', but split_details contains unequal values.",
                        'raw_row_data': row,
                        'suggested_action': self.suggest_action(row)
                    })

            elif stype == 'percentage':
                if not any('%' in part for part in details.split(';')):
                    anomalies.append({
                        'row_reference': f"row {row['_row_index']}",
                        'description': "Declared split_type is 'percentage', but split_details does not contain '%' signs.",
                        'raw_row_data': row,
                        'suggested_action': self.suggest_action(row)
                    })

            elif stype == 'shares':
                if '%' in details:
                    anomalies.append({
                        'row_reference': f"row {row['_row_index']}",
                        'description': "Declared split_type is 'shares', but split_details contains '%' signs.",
                        'raw_row_data': row,
                        'suggested_action': self.suggest_action(row)
                    })

        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Flag inconsistency. Require user review before import. Never silently recalculate splits."
