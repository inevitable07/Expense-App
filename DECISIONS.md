# Architecture Decisions

## Authentication Strategy

For the initial setup of the shared expenses application, we opted for Django's built-in session-based authentication rather than alternatives like Django REST Framework (DRF) token authentication or django-allauth. 

### Why this approach was chosen:
1. **Out-of-the-Box Security:** Standard session authentication automatically manages CSRF protection, secure HTTP-only cookies, and session lifecycle validation, reducing custom security implementation overhead.
2. **Simplified Architecture:** By utilizing native Django forms, templates, and views, we avoid adding large external dependencies (like `django-allauth`) which require heavy database migrations and configurations.
3. **Template Compatibility:** Since the setup specifies rendering Bootstrap-styled HTML templates for login and signup locally, standard Django sessions fit perfectly, whereas DRF Token auth is designed for stateless REST APIs accessed by decoupled single-page applications (SPAs) or mobile apps.

## Debt Simplification Algorithm

The simplify_debts function reduces the number of payment transactions needed to settle all outstanding balances within a group. It works as follows:

1. Compute the net balance for every member in the group.
   - Positive balance = the group collectively owes this person money.
   - Negative balance = this person owes the group money.

2. Separate members into two lists:
   - Creditors: members with positive balances (they are owed money).
   - Debtors: members with negative balances (they owe money).

3. Sort creditors by balance descending (largest owed first).
   Sort debtors by balance ascending (most negative first, i.e. largest debt first).

4. Greedily match the largest creditor with the largest debtor:
   - The transfer amount is the minimum of the creditor's remaining balance and the debtor's remaining debt (absolute value).
   - Subtract the transfer from both sides.
   - If a creditor or debtor reaches zero, move to the next one.

5. Repeat until all balances are settled.

### Invariants (enforced by design and tests):
- **Preserve Total Balances:** The algorithm preserves total balances exactly.
- **No Money Creation:** No individual transaction exceeds any individual's original balance.
- **No Money Destruction:** The sum of all output transaction amounts equals the total positive balances (which equals the absolute sum of total negative balances).
- **Conserved Flows:** Sum of credits equals sum of debits across all simplified transactions, leaving everyone's net position at zero after execution.

