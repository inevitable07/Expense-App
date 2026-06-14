import re
from .base import AnomalyDetector

class InvalidDateDetector(AnomalyDetector):
    """
    Checks if a row's date is invalid, unparseable, or format-ambiguous.

    Why: Date fields are critical for membership window constraints and foreign exchange lookups.
    Silently re-writing or guessing dates is unsafe for audit trails.

    False-Positive Risks:
        Standard dates that look ambiguous (e.g. 05-06-2026) but are intended in a specific
        group-wide format will be flagged.
    """

    @property
    def anomaly_type(self) -> str:
        return 'INVALID_DATE'

    def detect(self, rows: list[dict], group=None) -> list[dict]:
        anomalies = []
        for row in rows:
            date_str = self.get_field(row, 'date')
            if not date_str:
                continue

            parsed_date = self.parse_date(date_str)
            if not parsed_date:
                anomalies.append({
                    'row_reference': f"row {row['_row_index']}",
                    'description': f"Date parsing failed or format is invalid: '{date_str}'.",
                    'raw_row_data': row,
                    'suggested_action': self.suggest_action(row)
                })
            else:
                # Check for DD/MM/YYYY vs MM/DD/YYYY ambiguity:
                # If day <= 12 and month <= 12 and day != month
                parts = re.split(r'[-/]', date_str)
                if len(parts) >= 2:
                    try:
                        p1 = int(parts[0])
                        p2 = int(parts[1])
                        if 1 <= p1 <= 12 and 1 <= p2 <= 12 and p1 != p2:
                            anomalies.append({
                                'row_reference': f"row {row['_row_index']}",
                                'description': f"Ambiguous date format '{date_str}' (could be Day/Month or Month/Day).",
                                'raw_row_data': row,
                                'suggested_action': self.suggest_action(row)
                            })
                    except ValueError:
                        pass
        return anomalies

    def suggest_action(self, raw_row: dict) -> str:
        return "Present possible interpretations. Require confirmation. Never silently rewrite dates."
