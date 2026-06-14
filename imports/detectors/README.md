# Importer Anomaly Detectors

This directory contains the pluggable validation rules used by the CSV imports pipeline.

## How to Add a New Anomaly Detector

During live operations or to handle new validations, you can create a custom detector in 5 simple steps:

1. **Create the Detector Class**
   Inherit from the base `AnomalyDetector` class:
   ```python
   from imports.detectors.base import AnomalyDetector

   class CurrencyValidationDetector(AnomalyDetector):
       """
       Flags rows containing un-supported currency fields.
       """
       @property
       def anomaly_type(self) -> str:
           return 'UNSUPPORTED_CURRENCY'

       def detect(self, rows: list[dict]) -> list[dict]:
           anomalies = []
           for row in rows:
               currency = row.get('currency', '').upper()
               if currency and currency not in ['INR', 'USD']:
                   anomalies.append({
                       'row_reference': f"row {row['_row_index']}",
                       'description': f"Currency '{currency}' is not supported.",
                       'raw_row_data': row,
                       'suggested_action': self.suggested_action(row)
                   })
           return anomalies

       def suggest_action(self, raw_row: dict) -> str:
           return "Convert currency to INR or reject the row."
   ```

2. **Register the Detector in the Pipeline**
   Add your new class to the active registry list in `imports/pipeline.py`:
   ```python
   def get_detectors() -> list[AnomalyDetector]:
       return [
           DuplicateRowDetector(),
           NegativeAmountDetector(),
           CurrencyValidationDetector(),  # Newly added detector
       ]
   ```

3. **Verify via Tests**
   Write unit tests in `imports/tests.py` passing matching mock CSV rows to assert your detector flags the correct row indices and outputs the expected metadata dictionary.
