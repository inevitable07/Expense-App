# Expense Scoping and Group Memberships

In the shared expenses application, the membership date range (`joined_at` to `left_at`) on the `GroupMembership` model is the primary mechanism that scopes expenses to members.

## How it works

An expense is incurred on a specific date. To determine who is responsible for splitting a given expense within a group, the application checks if the user was an active member of that group on that specific date.

### Scoping Rule:
A user is eligible to share in an expense if and only if:
$$\text{joined\_at} \le \text{expense\_date} \le \text{left\_at (or Present)}$$

### Benefits:
1. **Accurate Historical Ledgers:** Users who join late are not charged for expenses incurred before their arrival.
2. **Seamless Group Offboarding:** Users who leave the group do not participate in splits for expenses created after their departure.
3. **Traceability:** Prevents balance corruption by binding ledger entries to strict, validated date ranges.
