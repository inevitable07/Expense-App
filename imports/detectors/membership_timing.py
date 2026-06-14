from .base import AnomalyDetector, resolve_user_by_name

class MembershipTimingDetector(AnomalyDetector):
    """
    Checks if the expense date falls outside any active group membership window
    for participants (payer or split members).

    Why: Users should not be charged or credited for group expenses incurred
    before they joined or after they left.

    False-Positive Risks:
        Legitimate grace periods or transitional expenses could be flagged.
    """

    @property
    def anomaly_type(self) -> str:
        return 'MEMBERSHIP_TIMING'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        if not group:
            return []

        anomalies = []
        if not hasattr(group, '_prefetched_memberships'):
            group._prefetched_memberships = list(group.memberships.select_related('user').all())
        memberships = group._prefetched_memberships

        for row in rows:
            date_str = self.get_field(row, 'date')
            parsed_date = self.parse_date(date_str)
            if not parsed_date:
                continue

            # Gather all participant names in row
            payer_name = self.get_field(row, 'paid_by', 'paidby', 'payer')
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

            for user in all_participants:
                user_mems = [m for m in memberships if m.user_id == user.id]
                if not user_mems:
                    continue

                # Check if the date is inside at least one membership window
                inside = False
                for mem in user_mems:
                    joined = mem.joined_at
                    left = mem.left_at
                    if joined <= parsed_date and (left is None or parsed_date <= left):
                        inside = True
                        break

                if not inside:
                    joined_str = str(user_mems[0].joined_at)
                    left_str = str(user_mems[0].left_at) if user_mems[0].left_at else "Present"
                    anomalies.append({
                        'row_reference': f"row {row['_row_index']}",
                        'description': f"Expense date {parsed_date} is outside active membership of {user.name} (Window: {joined_str} to {left_str}).",
                        'raw_row_data': row,
                        'suggested_action': self.suggest_action(row)
                    })
                    break  # Flag row once

        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Flag for review. Allow user to modify participants or memberships."
