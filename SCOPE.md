# Project Scope and Database Schema

This document details the database schema and the automated anomaly detection registry implemented in the ExpenseApp system.

---

## 1. Database Schema

The application database schema is composed of the following models:

### custom `User` (`accounts.User`)
Extends Django's `AbstractUser` to use `email` as the primary login credential.
- `email` (EmailField, unique=True): User's email address and unique identifier.
- `name` (CharField, max_length=255): User's full name.
- *Plus inherited Django authentication fields (e.g. password, groups, user_permissions, dates).*

### `Group` (`groups.Group`)
Represents an expense-sharing group.
- `name` (CharField, max_length=255): Display name of the group.
- `created_at` (DateTimeField, auto_now_add=True): Timestamp of creation.
- `created_by` (ForeignKey to User): Reference to the group creator.

### `GroupMembership` (`groups.GroupMembership`)
Represents a time-bound membership of a user in a group.
- `group` (ForeignKey to Group): Associated group.
- `user` (ForeignKey to User): Associated user.
- `joined_at` (DateField): The date the user joined the group.
- `left_at` (DateField, null=True, blank=True): The date the user left the group (null if currently active).

### `Expense` (`expenses.Expense`)
Represents a logged expense transaction.
- `group` (ForeignKey to Group): Group context.
- `paid_by` (ForeignKey to User): Debtor user who made the payment.
- `description` (CharField, max_length=255): What was purchased.
- `date` (DateField): Date of transaction.
- `original_amount` (DecimalField, max_digits=12, decimal_places=2): Amount in the original currency.
- `original_currency` (CharField, max_length=3): ISO code of original currency (`INR` or `USD`).
- `amount_inr` (DecimalField, max_digits=12, decimal_places=2): Converted amount in base currency (INR).
- `fx_rate_used` (ForeignKey to FXRate, null=True, blank=True): Exchange rate reference.
- `split_type` (CharField, max_length=15): Strategy code (`EQUAL`, `EXACT`, `PERCENTAGE`, `SHARES`).
- `status` (CharField, max_length=15): State (`ACTIVE`, `VOID`, `SUPERSEDED`).
- `source` (CharField, max_length=15): Origin (`MANUAL`, `IMPORTED`).
- `import_batch` (ForeignKey to ImportBatch, null=True, blank=True): Reference to the import batch.

### `ExpenseSplit` (`expenses.ExpenseSplit`)
Stores calculated individual user debt portions.
- `expense` (ForeignKey to Expense): Parent expense.
- `user` (ForeignKey to User): Debtor user.
- `share_amount_inr` (DecimalField, max_digits=12, decimal_places=2): User's calculated debt portion in INR.

### `Settlement` (`settlements.Settlement`)
Represents a direct peer-to-peer debt resolution payment.
- `group` (ForeignKey to Group): Group context.
- `paid_by` (ForeignKey to User): Payer (debtor).
- `paid_to` (ForeignKey to User): Recipient (creditor).
- `amount_inr` (DecimalField, max_digits=12, decimal_places=2): Amount transferred.
- `date` (DateField): Date of payment.
- `note` (TextField, blank=True): Notes/reference code.

### `FXRate` (`core.FXRate`)
Represents a conversion exchange rate.
- `from_currency` (CharField, max_length=3): Source currency (e.g. `USD`).
- `to_currency` (CharField, max_length=3): Target currency (e.g. `INR`).
- `rate` (DecimalField, max_digits=12, decimal_places=6): Exchange rate multiplier.
- `effective_date` (DateField): Validity date.
- *Unique Constraint: `('from_currency', 'to_currency', 'effective_date')`*

### `ImportBatch` (`imports.ImportBatch`)
Tracks upload batch metadata.
- `uploaded_at` (DateTimeField, auto_now_add=True): Upload timestamp.
- `uploaded_by` (ForeignKey to User): Uploader.
- `group` (ForeignKey to Group): Target group.
- `status` (CharField, max_length=30): Approval status (`PENDING_REVIEW`, `APPROVED`, `REJECTED`, `PARTIALLY_APPLIED`).
- `raw_file` (FileField): Uploaded CSV/JSON file.
- `description` (CharField, max_length=255): Batch info.

### `ImportAnomaly` (`imports.ImportAnomaly`)
Represents a flagged data conflict in a batch.
- `import_batch` (ForeignKey to ImportBatch): Associated batch.
- `row_reference` (CharField, max_length=100): E.g. `"row 12"`.
- `anomaly_type` (CharField, max_length=100): Unique classification token.
- `description` (TextField): Explanation of the issue.
- `raw_row_data` (JSONField): Original fields from the parser.
- `suggested_action` (TextField): Resolution recommendation.
- `final_action` (TextField, null=True, blank=True): The manually applied override action text.
- `status` (CharField, max_length=30): Review state (`PENDING`, `APPROVED`, `REJECTED`, `MODIFIED`).

---

## 2. Complete Anomaly Detection Registry

The system runs 15 anomaly checks on every uploaded CSV file. Below is the full detector list:

| Detector Class | Anomaly Type | Checking Policy | Rationale |
| :--- | :--- | :--- | :--- |
| `DuplicateExpenseDetector` | `DUPLICATE_EXPENSE` | Checks for lines with identical `date`, `description`, `paid_by` (payer), and `amount` within the batch. | Helps identify double-entered records that represent the exact same expense, prompting the reviewer to decide which entry to keep. |
| `ConflictingDuplicatesDetector` | `CONFLICTING_DUPLICATES` | Finds rows that share identical `date`, `description`, and `payer` but have different amounts, currencies, or splits. | Mismatches on what should be the same logged transaction require human validation to determine which record is correct. |
| `NegativeAmountDetector` | `NEGATIVE_AMOUNT` | Flags rows where the parsed amount is less than `0.0`. | Negative quantities in amount columns are flagged to avoid sign confusion and suggest refund categorization. |
| `MissingCurrencyDetector` | `MISSING_CURRENCY` | Flags rows where the currency column is empty. | Currency must be explicitly logged to calculate splits correctly. |
| `UnsupportedCurrencyDetector` | `UNSUPPORTED_CURRENCY` | Flags rows where the currency is not in `INR` or `USD`. | The system only supports INR and USD; other currencies cannot be processed automatically. |
| `ZeroAmountDetector` | `ZERO_AMOUNT` | Flags rows where the parsed amount is exactly `0.0`. | Prevent blank/empty transactions from bloating records. |
| `MissingPayerDetector` | `MISSING_PAYER` | Flags rows where the payer (`paid_by`) field is empty or missing. | Every transaction must have a valid payer to track credits correctly. |
| `SettlementMisclassificationDetector` | `SETTLEMENT_MISCLASSIFICATION` | Detects settlement/reimbursement keywords (e.g., *settled*, *paid back*) in descriptions when no split details are provided. | Settlements do not represent new spending, but transfer of funds, so they should be categorized as Settlement records. |
| `InvalidDateDetector` | `INVALID_DATE` | Flags unparseable date formats or ambiguous dates. | Unparseable dates prevent correct scoping and temporal queries. |
| `MembershipTimingDetector` | `MEMBERSHIP_TIMING` | Checks if transaction dates fall outside the membership windows of any participants. | Users should not be charged or credited for group expenses incurred before they joined or after they left. |
| `UnknownUserDetector` | `UNKNOWN_USER` | Identifies payers or split participants who cannot be resolved in the group memberships or system directories. | Preventing unknown user records from silently blocking ledger operations. |
| `InvalidSplitDetector` | `INVALID_SPLIT` | Assures that percentages sum to 100%, exact splits sum to the total amount, and share counts are non-negative. | Ensure the ledger is mathematically balanced. |
| `MissingRequiredFieldsDetector` | `MISSING_REQUIRED_FIELDS` | Flags rows missing amount, date, description, or paid_by fields. | Avoid saving incomplete records. |
| `SplitTypeMismatchDetector` | `SPLIT_TYPE_MISMATCH` | Flags rows where split details don't match the selected split type (e.g. details given on EQUAL split). | Prevent logical inconsistencies in splitting shares. |
| `MembershipChangeEventDetector` | `MEMBERSHIP_CHANGE_EVENT` | Detects descriptions indicating join/leave events, or expenses outside active membership windows. | Historical membership updates require updating membership windows rather than logging invalid rows. |
