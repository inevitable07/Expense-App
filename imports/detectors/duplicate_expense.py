from .base import AnomalyDetector

class DuplicateExpenseDetector(AnomalyDetector):
    """
    Flags rows that appear to be duplicate expense entries in the same upload batch.

    Why: Helps identify double-entered records that represent the exact same expense,
    prompting the reviewer to decide which entry to keep.

    False-Positive Risks:
        Two separate, legitimate purchases of the exact same amount at the same store
        on the same day (e.g. buying two separate movie tickets) will be flagged.
    """

    @property
    def anomaly_type(self) -> str:
        return 'DUPLICATE_EXPENSE'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        """
        Scans for rows with identical date, description, paid_by, and amount.
        """
        anomalies = []
        seen = {}  # key: (date, description, paid_by, amount), value: list of row_indices

        for row in rows:
            date = self.get_field(row, 'date')
            desc = self.get_field(row, 'description').strip().lower()
            paid_by = self.get_field(row, 'paid_by', 'paidby', 'payer', default="").strip().lower()
            amount = self.get_field(row, 'amount').strip()

            if not date or not desc or not amount:
                continue


            # Resolve amount value cleaned to be safe
            try:
                amt_cleaned = str(self.clean_amount(amount))
            except ValueError:
                amt_cleaned = amount

            key = (date, desc, paid_by, amt_cleaned)
            seen.setdefault(key, []).append(row['_row_index'])

        # Flag all rows that have duplicates
        for key, lines in seen.items():
            if len(lines) > 1:
                for line in lines:
                    other_lines = [l for l in lines if l != line]
                    raw_row = next(r for r in rows if r['_row_index'] == line)
                    anomalies.append({
                        'row_reference': f"row {line}",
                        'description': f"Potential duplicate of row(s) {', '.join(map(str, other_lines))}.",
                        'raw_row_data': raw_row,
                        'suggested_action': self.suggest_action(raw_row, other_lines)
                    })

        return anomalies

    def suggest_action(self, raw_row: dict, other_lines: list = None) -> str:
        """
        Recommends reviewing duplicate rows and keeping only one.
        """
        if other_lines:
            lines_str = f"row {other_lines[0]}" if len(other_lines) == 1 else f"rows {other_lines}"
            return f"Verify duplicate status with {lines_str}. Keep one entry and reject the other."
        return "Verify duplicate status. Keep one entry and reject the other."
