from abc import ABC, abstractmethod

class AnomalyDetector(ABC):
    """
    Abstract base class for CSV import anomaly detectors.

    Why: Defines a common interface so that any validation rule checks can be
    isolated, tested individually, and registered dynamically into the import pipeline.
    """

    @property
    @abstractmethod
    def anomaly_type(self) -> str:
        """
        Why: Returns a unique string identifier identifying the classification of anomaly
        (e.g., 'DUPLICATE_ROW', 'NEGATIVE_AMOUNT').
        """
        pass

    @abstractmethod
    def detect(self, rows: list[dict]) -> list[dict]:
        """
        Analyzes a set of parsed rows to detect anomalies.

        Why: Subclasses must implement their custom detection logic.

        Parameters:
            rows (list of dict): Parsed CSV row dictionaries, each including a '_row_index' field.

        Returns:
            list of dict: Anomaly detail dictionaries containing keys matching ImportAnomaly fields:
                - row_reference: str (e.g. "row 12")
                - description: str
                - raw_row_data: dict
                - suggested_action: str
        """
        pass

    @abstractmethod
    def suggest_action(self, raw_row: dict) -> str:
        """
        Provides a recommended resolution action statement for a flagged row.

        Why: Ensures every anomaly has a clear suggestion before human intervention.

        Parameters:
            raw_row (dict): The original row data.

        Returns:
            str: Suggested resolution action details.
        """
        pass
