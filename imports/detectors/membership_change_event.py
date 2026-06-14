from .base import AnomalyDetector, resolve_user_by_name

class MembershipChangeEventDetector(AnomalyDetector):
    """
    Checks for rows containing cues of membership change events (joined, left, farewell)
    or where expenses are inconsistent with current GroupMembership windows.

    Why: Groups change members over time. Logging expenses for historical members or users
    who have not joined requires membership updates to remain auditable.

    False-Positive Risks:
        Keywords found in other context (e.g. description 'Farewell dinner for project'
        even though no group membership changed).
    """

    @property
    def anomaly_type(self) -> str:
        return 'MEMBERSHIP_CHANGE_EVENT'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        keywords = ['moving in', 'moving out', 'joined', 'left the group', 'farewell', 'deposit share']

        for row in rows:
            desc = self.get_field(row, 'description').lower()
            notes = self.get_field(row, 'notes', 'note').lower()

            flagged = False
            if any(kw in desc for kw in keywords) or any(kw in notes for kw in keywords):
                flagged = True
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': "Row description or notes indicate a group membership change event.",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row)
                })

            if not flagged and group:
                date_str = self.get_field(row, 'date')
                parsed_date = self.parse_date(date_str)
                if parsed_date:
                    # Gather participant users
                    payer_name = self.get_field(row, 'paid_by', 'payer')
                    payer_user = resolve_user_by_name(payer_name, group)

                    split_with_str = self.get_field(row, 'split_with', 'spilit_with')
                    split_users = []
                    if split_with_str:
                        for name in split_with_str.split(';'):
                            if name.strip():
                                u = resolve_user_by_name(name, group)
                                if u:
                                    split_users.append(u)

                    all_participants = set()
                    if payer_user:
                        all_participants.add(payer_user)
                    all_participants.update(split_users)

                    if not hasattr(group, '_prefetched_memberships'):
                        group._prefetched_memberships = list(group.memberships.select_related('user').all())

                    for user in all_participants:
                        user_mems = [m for m in group._prefetched_memberships if m.user_id == user.id]
                        if user_mems:
                            outside = True
                            for mem in user_mems:
                                joined = mem.joined_at
                                left = mem.left_at
                                if joined <= parsed_date and (left is None or parsed_date <= left):
                                    outside = False
                                    break
                            if outside:
                                anomalies.append({
                                    'row_reference': f"row {row['_row_index']}",
                                    'description': f"User {user.name} appears in expense on {parsed_date} outside their membership history window.",
                                    'raw_row_data': row,
                                    'suggested_action': self.suggest_action(row)
                                })
                                break

        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Suggest creation or update of GroupMembership records. Require approval before modifying membership history."
