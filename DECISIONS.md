# Architectural Decisions Log

This document chronicles the fundamental design decisions made during the architecture and construction of the Shared Expense Tracker.

---

## 1. Time-Bound Group Membership Scoping

### Problem
In multi-user groups, memberships are dynamic. Users join and leave groups over time. If a user joins a group on June 1st, they should not be charged for a group rent expense incurred on May 1st. Standard Django Many-to-Many relationships do not track historical time windows, causing historical ledger recalculations to incorrectly charge users who were not active members at the time.

### Alternatives
- **Alternative A**: A standard Many-to-Many field (`members = models.ManyToManyField(User)`) on the `Group` model.
- **Alternative B**: A custom time-bound membership model containing join and leave date boundaries.

### Chosen Option
We implemented **Alternative B** via the [GroupMembership](file:///e:/ExpenseApp/groups/models.py#L41-L84) model. It contains:
- `joined_at` (DateField)
- `left_at` (DateField, nullable)

The net balance engine functions `_get_membership_date_ranges` and `_get_eligible_expense_ids` in [balances/engine.py](file:///e:/ExpenseApp/balances/engine.py#L186-L258) inspect these date windows to filter which expenses a user is responsible for.

### Rejected Options
- **Alternative A (Simple Many-to-Many)**: Rejected because it cannot represent historical states. If Meera leaves the group, removing her would wipe out her historical share data, whereas keeping her as a member forever would continue to allocate a share of new expenses to her.

### Long-Term Consequences
- **Positive**: Complete audit compliance. Recalculating group balances at any point in time accurately reflects the real-world membership status on that day.
- **Negative**: Adds database lookup complexity. Balance engine logic must do range queries against `GroupMembership` rather than a simple table join.

---

## 2. Separate Table for Expense Splits (`ExpenseSplit`)

### Problem
Each `Expense` has multiple participants, each responsible for a specific portion of the total cost depending on the split type (Equal, Exact, Percentage, Shares). Storing these computed splits inline on the `Expense` model is challenging.

### Alternatives
- **Alternative A**: Store split configurations and calculated shares inside a `JSONField` on the `Expense` model.
- **Alternative B**: Create a separate relational table [ExpenseSplit](file:///e:/ExpenseApp/expenses/models.py#L180-L212).

### Chosen Option
We implemented **Alternative B** by creating the `ExpenseSplit` model. It defines:
- `expense` (ForeignKey to Expense)
- `user` (ForeignKey to User)
- `share_amount_inr` (DecimalField)

Calculating the splits is isolated in the service function `compute_splits` inside `expenses/services.py` and saved as distinct database records.

### Rejected Options
- **Alternative A (JSONField)**: Rejected because running SQL aggregations (like summing total debts across multiple groups or generating user-specific ledger breakdowns) is inefficient and hard to index in standard SQL databases. Relational foreign key cascades are also lost when users are deleted.

### Long-Term Consequences
- **Positive**: Standard relational database operations work flawlessly. We can use Django ORM aggregates like `Sum('share_amount_inr')` directly in `get_user_net_balance` inside [balances/engine.py](file:///e:/ExpenseApp/balances/engine.py#L261-L320), making financial queries extremely fast.
- **Negative**: Creates more database rows (N splits per expense), requiring careful indexing on `expense_id` and `user_id`.

---

## 3. Dedicated Settlement Model (`Settlement`)

### Problem
Peer-to-peer transfers are needed to settle balances (e.g. Rohan pays Aisha 5,000 INR). These transactions are structurally different from standard expenses: they do not represent new group spending, they do not have multiple split shares, and they only involve two individuals.

### Alternatives
- **Alternative A**: Model settlements as a special subtype of `Expense` (e.g. split equally between two people with custom flags).
- **Alternative B**: Create a dedicated [Settlement](file:///e:/ExpenseApp/settlements/models.py#L6-L40) model.

### Chosen Option
We implemented **Alternative B**. The `Settlement` model defines:
- `group` (ForeignKey to Group)
- `paid_by` (ForeignKey to User)
- `paid_to` (ForeignKey to User)
- `amount_inr` (DecimalField)
- `date` (DateField)

Calculations in `_get_settlement_net` inside [balances/engine.py](file:///e:/ExpenseApp/balances/engine.py#L73-L113) aggregate these records to adjust users' balances.

### Rejected Options
- **Alternative A (Subtyped Expense)**: Rejected because it pollutes group spending metrics. Summing the total cost of all `Expense` objects in a group would include settlements, artificially bloating the calculated group cost.

### Long-Term Consequences
- **Positive**: Separates payments from expenses cleanly. Group analytics dashboards can show real consumption expenditure versus settle-up payments.
- **Negative**: Code complexity is slightly increased as balance engine queries must sum records from both `ExpenseSplit` and `Settlement` tables.

---

## 4. Rounding Policy in Split Calculations

### Problem
When splitting an expense of 100 INR equally among 3 people, the exact share is 33.3333... INR. Representing this in a standard 2-decimal financial database requires rounding. If we round to 33.33 INR, the sum is 99.99 INR, leaving a lost penny of 0.01 INR. This causes database validation constraints to fail when comparing the sum of splits against the total expense amount.

### Alternatives
- **Alternative A**: Float math (using python float type) and displaying rounded values in UI.
- **Alternative B**: Exact Decimal math using `ROUND_HALF_UP` and allocating the rounding remainder (the "lost penny") to one of the participants.

### Chosen Option
We implemented **Alternative B** using Django's `Decimal` and Python's `decimal.ROUND_HALF_UP` inside the `compute_splits` service function in `expenses/services.py`. The algorithm distributes rounded shares to all participants, sums the results, computes the difference from the total `amount_inr`, and allocates the remainder to the payer of the expense, ensuring that:
$$\sum \text{Splits} = \text{Expense Amount}$$

### Rejected Options
- **Alternative A (Float math)**: Rejected because floating point representation issues (e.g. `0.1 + 0.2 = 0.30000000000000004`) lead to balance leaks and un-auditable ledgers.

### Long-Term Consequences
- **Positive**: 100% mathematical precision. The database matches ledger constraints at all times.
- **Negative**: The payer of the expense might pay or receive a fraction of a penny more or less than others, though this is negligible.

---

## 5. Greedy Debt Simplification Algorithm

### Problem
In a group of N members, everyone paying each other bilaterally can result in up to $N(N-1)/2$ transfers. For example, if Aisha owes Rohan, and Rohan owes Priya, Aisha could just pay Priya directly, eliminating one transaction.

### Alternatives
- **Alternative A**: Bilateral settlement (each person pays their exact net debt to every counterparty individually).
- **Alternative B**: Netting balances and matching net creditors and debtors greedily.

### Chosen Option
We implemented **Alternative B** via the `simplify_debts` engine function inside [balances/engine.py](file:///e:/ExpenseApp/balances/engine.py#L370-L450). It sums all credits/debits per user to get their single net position, splits users into net creditors and debtors, and greedily resolves the largest debtor with the largest creditor until all balances are zero.

### Rejected Options
- **Alternative A (Bilateral)**: Rejected because it causes an excessive number of transactions, making it highly inconvenient for groups of friends.

### Long-Term Consequences
- **Positive**: Minimizes transactions to at most $N-1$ transfers, simplifying peer-to-peer settle-ups.
- **Negative**: The matches are mathematical and do not preserve who historically owed whom directly (e.g. Aisha pays Priya even though Aisha only consumed Rohan's items).

---

## 6. Currency Conversion and Daily Exchange Rates

### Problem
Expenses can be logged in `INR` or `USD`. However, ledger calculations and net balance simplify-debts engines require a single base currency (`INR`). Currency rates change daily, so conversion must be tied to the specific transaction date.

### Alternatives
- **Alternative A**: Convert values at the time of query using a live web API.
- **Alternative B**: Query an database table [FXRate](file:///e:/ExpenseApp/core/models.py#L3-L43) for a conversion multiplier matching the transaction `effective_date`.

### Chosen Option
We implemented **Alternative B**. The `Expense` model clean function converts `original_amount` to `amount_inr` using the associated `FXRate` record effective on that day. The conversion is saved statically in `amount_inr` at the time of database save.

### Rejected Options
- **Alternative A (Live API)**: Rejected because web requests introduce query latency, fail when offline, and historical currency values can shift, causing historical ledgers to fluctuate.

### Long-Term Consequences
- **Positive**: Immutable audit trail. Converted rates are locked in the database.
- **Negative**: Fails to save the record if no exchange rate is seeded for that date. To solve this, the CSV applier parses Meera's custom decisions to dynamically seed missing rates.

---

## 7. Import Approval Workflow Design (Meera's Approval Gate)

### Problem
CSV uploads are highly error-prone (typos, negative values, missing payers, duplicate transactions). Directly inserting raw data into the ledger can pollute the database.

### Alternatives
- **Alternative A**: Silently correct errors or automatically reject rows that fail validations during upload.
- **Alternative B**: Logging raw uploads as `ImportBatch` and creating `ImportAnomaly` entries for each flagged issue, requiring manual user resolution (Approve, Reject, Modify) before applying to models.

### Chosen Option
We implemented **Alternative B** in [imports/pipeline.py](file:///e:/ExpenseApp/imports/pipeline.py) and [imports/views.py](file:///e:/ExpenseApp/imports/views.py#L54-L128). An upload parses rows, runs 15 detectors, and saves them. The batch is held as `PENDING_REVIEW` until all anomalies are resolved in the review UI, at which point `apply_import` in `imports/applier.py` runs.

### Rejected Options
- **Alternative A (Silent fix)**: Rejected because automated corrections can lead to incorrect ledger mappings without uploader awareness.

### Long-Term Consequences
- **Positive**: Clean audit history. No raw row enters the database ledger without manual validation.
- **Negative**: Uploading files is not fully automated; it requires an explicit user review step.
