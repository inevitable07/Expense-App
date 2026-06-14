from .base import AnomalyDetector, resolve_user_by_name

class UnknownUserDetector(AnomalyDetector):
    """
    Checks if a row references any user who cannot be matched to a database user.

    Why: Preventing unknown user records from silently blocking ledger operations.

    False-Positive Risks:
        Nicknames or typos in usernames/emails that are clear to humans will be flagged.
    """

    @property
    def anomaly_type(self) -> str:
        return 'UNKNOWN_USER'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []

        for row in rows:
            unknowns = []

            # 1. Check payer
            payer_name = self.get_field(row, 'paid_by', 'paidby', 'payer')
            if payer_name and not resolve_user_by_name(payer_name, group):
                unknowns.append(payer_name)

            # 2. Check split_with participants
            split_with_str = self.get_field(row, 'split_with', 'spilit_with')
            if split_with_str:
                for name in split_with_str.split(';'):
                    name = name.strip()
                    if name and not resolve_user_by_name(name, group):
                        unknowns.append(name)

            # 3. Check split_details (in case there's another name)
            details_str = self.get_field(row, 'split_details', 'spilit_details')
            if details_str:
                for part in details_str.split(';'):
                    part = part.strip()
                    if part:
                        tokens = part.rsplit(None, 1)
                        if tokens:
                            name = tokens[0].strip()
                            if name and not resolve_user_by_name(name, group):
                                unknowns.append(name)

            # Deduplicate unknowns
            unique_unknowns = sorted(list(set(unknowns)))
            if unique_unknowns:
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': f"Unknown user reference(s): {', '.join(unique_unknowns)}.",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row)
                })

        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Map to existing user or create user manually."
