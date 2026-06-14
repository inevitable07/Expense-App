from .base import AnomalyDetector

class ConflictingDuplicatesDetector(AnomalyDetector):
    """
    Checks for conflicting duplicates where the same date, description, and payer
    contain different amounts, currencies, or split details.

    Why: Mismatches on what should be the same logged transaction require human validation
    to determine which record is correct.

    False-Positive Risks:
        Multiple distinct transactions on the same day with the same description and payer,
        but different values (e.g. buying a ticket in morning and afternoon) will be flagged.
    """

    @property
    def anomaly_type(self) -> str:
        return 'CONFLICTING_DUPLICATES'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        seen = {}  # key: (date, description, paid_by), value: list of rows

        for row in rows:
            date = self.get_field(row, 'date').strip()
            desc = self.get_field(row, 'description').strip().lower()
            paid_by = self.get_field(row, 'paid_by', 'payer').strip().lower()

            if not date or not desc or not paid_by:
                continue

            key = (date, desc, paid_by)
            seen.setdefault(key, []).append(row)

        for key, r_list in seen.items():
            if len(r_list) > 1:
                # Compare fields to check for conflicts
                # Conflict is when amount, currency, split_type, split_with, or split_details differ
                first = r_list[0]
                has_conflict = False
                for r in r_list[1:]:
                    if (self.get_field(first, 'amount') != self.get_field(r, 'amount') or
                        self.get_field(first, 'currency') != self.get_field(r, 'currency') or
                        self.get_field(first, 'split_type', 'spilit_type') != self.get_field(r, 'split_type', 'spilit_type') or
                        self.get_field(first, 'split_with', 'spilit_with') != self.get_field(r, 'split_with', 'spilit_with') or
                        self.get_field(first, 'split_details', 'spilit_details') != self.get_field(r, 'split_details', 'spilit_details')):
                        has_conflict = True
                        break

                if has_conflict:
                    for r in r_list:
                        other_lines = [oth['_row_index'] for oth in r_list if oth['_row_index'] != r['_row_index']]
                        anomalies.append({
                            'row_reference': f"row {r['_row_index']}",
                            'description': f"Conflict duplicate: Same date, description, and payer, but different values compared to row(s) {', '.join(map(str, other_lines))}.",
                            'raw_row_data': r,
                            'suggested_action': self.suggest_action(r)
                        })

        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Present all candidate rows and require manual resolution."
