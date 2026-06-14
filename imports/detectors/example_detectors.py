from .base import AnomalyDetector

class DuplicateRowDetector(AnomalyDetector):
    """
    Scans for exact duplicate rows in the CSV payload.

    Why: Double-uploading or duplicating records leads to double-billing.
    We flag matching records so that duplicates can be skipped safely.
    """

    @property
    def anomaly_type(self) -> str:
        return 'DUPLICATE_ROW'

    def detect(self, rows: list[dict]) -> list[dict]:
        """
        Flags rows where all fields (excluding row metadata) match an earlier row.
        """
        anomalies = []
        seen_signatures = {}  # maps row signature tuple to row_index

        for row in rows:
            # Why: Exclude row tracking index to compare actual payload columns only
            signature = tuple(sorted((k, v) for k, v in row.items() if k != '_row_index'))

            if signature in seen_signatures:
                original_row_line = seen_signatures[signature]
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': f"Row is an exact duplicate of row {original_row_line}.",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row, duplicate_of=original_row_line)
                })
            else:
                seen_signatures[signature] = row['_row_index']

        return anomalies

    def suggest_action(self, raw_row: dict, duplicate_of: int = None) -> str:
        """
        Suggests skipping duplicate entries.
        """
        if duplicate_of:
            return f"Skip row (exact duplicate of row {duplicate_of})."
        return "Skip row (duplicate record)."


class NegativeAmountDetector(AnomalyDetector):
    """
    Scans for negative amounts in columns with transaction values.

    Why: Financial records should represent positive quantities. Negative amounts
    often represent system entry errors or refunds, requiring review and approval.
    """

    @property
    def anomaly_type(self) -> str:
        return 'NEGATIVE_AMOUNT'

    def detect(self, rows: list[dict]) -> list[dict]:
        """
        Scans all fields containing cost/amount keywords and flags any negative values.
        """
        anomalies = []
        amount_keywords = ['amount', 'cost', 'price', 'value', 'sum', 'total', 'charge']

        for row in rows:
            for col_name, value in row.items():
                if col_name == '_row_index':
                    continue

                # Why: Check if the column name matches our financial keywords (case-insensitive)
                if any(kw in col_name.lower() for kw in amount_keywords):
                    try:
                        # Why: Try parsing the value as a float to detect negative numbers
                        numeric_val = float(value)
                        if numeric_val < 0:
                            anomalies.append({
                                'row_reference': f"row {row['_row_index']}",
                                'description': f"Negative quantity '{value}' found in amount column '{col_name}'.",
                                'raw_row_data': row,
                                'suggested_action': self.suggest_action(row, col_name=col_name)
                            })
                    except (ValueError, TypeError):
                        # Why: Safe skip if the column doesn't hold parseable numeric values
                        pass

        return anomalies

    def suggest_action(self, raw_row: dict, col_name: str = "amount") -> str:
        """
        Recommends converting to absolute positive values or rejecting.
        """
        return f"Convert value in '{col_name}' to positive absolute value, or reject/modify."
