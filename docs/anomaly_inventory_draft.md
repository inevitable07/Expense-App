# CSV Anomaly Inventory (Draft)

This document records the anomalies identified during manual review of `expenses_export.csv`, along with the detection rules and handling policies that will be implemented in the import system.

---

## 1. Duplicate Expense Entries

### Description

The same expense appears multiple times in the dataset, either as an exact duplicate or with minor variations.

### Detection Rule

Flag rows where the following fields match:

* Date
* Description
* Payer
* Amount

Also flag near-duplicates where all fields match except the amount.

### Policy

* Do not automatically delete records.
* Mark all matching entries as potential duplicates.
* Require user review and approval before any action is taken.

### Suggested Action

Review and keep the correct entry; mark the others as superseded.

---

## 2. Negative Amount Entries (Refunds)

### Description

An expense contains a negative monetary value.

### Detection Rule

Amount < 0

### Policy

* Treat negative values as refunds rather than expenses.
* Refunds should be distributed according to the original split logic where possible.
* If the refund target cannot be determined confidently, require manual review.

### Suggested Action

Convert to refund transaction or request user confirmation.

---

## 3. Missing Currency Information

### Description

The currency field is empty or missing.

### Detection Rule

Currency field is NULL, blank, or invalid.

### Policy

* Do not assume INR or USD automatically.
* Missing currency information is considered ambiguous.
* Require user review.

### Suggested Action

Ask the user to specify the correct currency before import.

---

## 4. Zero Amount Expenses

### Description

An expense record contains an amount of zero.

### Detection Rule

Amount = 0

### Policy

* Flag as suspicious.
* Do not automatically import as a valid expense.

### Suggested Action

Review whether the row is accidental, informational, or should be discarded.

---

## 5. Missing Payer Information

### Description

The expense amount exists, but the payer is not specified.

### Detection Rule

Payer field is empty or invalid.

### Policy

* Do not automatically assign a payer.
* Expense ownership cannot be determined reliably.
* Require manual review.

### Suggested Action

Request the user to identify the payer.

---

## 6. Settlement Recorded as Expense

### Description

A debt repayment or settlement has been logged as an expense.

### Detection Rule

Description contains keywords such as:

* settled
* settlement
* paid back
* reimbursement
* returned money

or matches other settlement patterns.

### Policy

* Do not import as an expense.
* Suggest conversion into a Settlement record.

### Suggested Action

Reclassify the entry as a Settlement after user approval.

---

## 7. Ambiguous or Invalid Date Format

### Description

The date format is inconsistent, invalid, or cannot be interpreted confidently.

### Detection Rule

* Date parsing fails.
* Multiple interpretations are possible.
* Date format differs from expected format.

### Policy

* Do not silently correct dates.
* Present possible interpretations to the user.

### Suggested Action

Require user confirmation before import.

---

## 8. Expense Outside Membership Window

### Description

A user is included in an expense despite not being an active member at that time.

### Detection Rule

Expense date falls outside:

* joined_at
* left_at

membership range.

### Policy

* Flag for review.
* Do not automatically modify participants.

### Suggested Action

Review participant eligibility based on membership history.

---

## 9. Unknown User Reference

### Description

The CSV references a user who does not exist in the system.

### Detection Rule

Referenced user cannot be matched to any known member.

### Policy

* Do not create unknown users automatically.
* Require user review.

### Suggested Action

Map to an existing user or create a new user manually.

---

## 10. Invalid Split Configuration

### Description

Expense split values do not match the expense amount.

### Detection Rule

Examples:

* Exact splits do not sum to total expense.
* Percentages do not sum to 100%.
* Share counts are invalid.

### Policy

* Prevent automatic import.
* Require correction before processing.

### Suggested Action

Review and fix split values.

---

## 11. Missing Required Fields

### Description

Mandatory fields are absent.

### Detection Rule

Missing:

* Amount
* Date
* Description
* Payer
* Split information

### Policy

* Do not import incomplete records.

### Suggested Action

Require user correction.

---

## 12. Conflicting Duplicate Entries

### Description

Multiple records appear to represent the same expense but contain conflicting values.

### Detection Rule

Matching:

* Date
* Description
* Payer

but different:

* Amount
* Currency
* Split values

### Policy

* Treat as a conflict.
* Require manual resolution.

### Suggested Action

Present all candidate records for user review.

---

## 13. Unsupported Currency

### Description

The expense uses a currency not supported by the system.

### Detection Rule

Currency not in:

* INR
* USD

### Policy

* Prevent automatic import.
* Require review and conversion strategy.

### Suggested Action

Map to a supported currency or provide an exchange rate.

---

## 14. Split Type Mismatch

### Description

The expense declares one split type but the actual distribution data follows a different split strategy.

Examples:

Declared:

EQUAL

Actual:

* Aisha = 500
* Rohan = 300
* Priya = 200

or

Declared:

PERCENTAGE

Actual percentages do not sum to 100%.

### Detection Rule

Compare:

* split_type column
* split allocation data

Flag when the allocation does not match the declared split type.

### Policy

Do not silently recalculate splits.

Require user review.

### Suggested Action

Ask user whether:

* split_type is incorrect
* split allocation values are incorrect

Import only after approval.

---

## 15. Membership Change Events

### Description

The CSV contains information indicating that:

* a member joined the group
* a member left the group

but the membership history in the system does not match the imported data.

Examples:

* Sam joined in April
* Meera left in March

### Detection Rule

Detect rows indicating:

* join events
* leave events
* participant changes

or identify expenses referencing users outside their recorded membership window.

### Policy

Do not automatically modify membership history.

Require review.

### Suggested Action

Create or update GroupMembership records only after approval.

Membership changes must remain fully auditable.


# General Import Principle

The import system must never silently modify, delete, merge, or reinterpret financial data.

Every anomaly must:

1. Be detected.
2. Be recorded.
3. Be traceable.
4. Be reviewable.
5. Require explicit approval before application.

When uncertainty exists, the system must prefer user review over automatic correction.
