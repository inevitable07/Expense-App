"""
Balance Calculation Engine for Shared Expenses
================================================

This module provides the core financial logic for computing net balances,
generating traceable breakdowns, and simplifying debts within expense
sharing groups.

ARCHITECTURE OVERVIEW:
- Section 1: Settlement Extension Points (placeholder for future settlements module)
- Section 2: Net Balance Calculation (single-user balance)
- Section 3: Group Balances (all members)
- Section 4: Debt Simplification (greedy algorithm)
- Section 5: Balance Breakdown (traceable line-by-line audit)

These sections are intentionally separable so they can be staged and
committed independently.

DEBT SIMPLIFICATION ALGORITHM (for DECISIONS.md):
--------------------------------------------------
The simplify_debts function reduces the number of payment transactions
needed to settle all outstanding balances within a group. It works as
follows:

1. Compute the net balance for every member in the group.
   - Positive balance = the group collectively owes this person money.
   - Negative balance = this person owes the group money.

2. Separate members into two lists:
   - Creditors: members with positive balances (they are owed money).
   - Debtors: members with negative balances (they owe money).

3. Sort creditors by balance descending (largest owed first).
   Sort debtors by balance ascending (most negative first, i.e. largest debt first).

4. Greedily match the largest creditor with the largest debtor:
   - The transfer amount is the minimum of the creditor's remaining
     balance and the debtor's remaining debt (absolute value).
   - Subtract the transfer from both sides.
   - If a creditor or debtor reaches zero, move to the next one.

5. Repeat until all balances are settled.

INVARIANTS (enforced by tests):
- The algorithm never creates money: no output transaction exceeds
  any individual's original balance.
- The algorithm never destroys money: sum of all output transaction
  amounts equals the total positive balances (which equals the
  absolute sum of total negative balances).
- After all transactions, every member's net position is zero.
--------------------------------------------------

SETTLEMENT INTEGRATION:
The Settlement model does not exist yet. All settlement-related queries
are isolated in _get_settlement_net() and _get_settlement_rows().
When the settlements module is built, ONLY these two functions need updating.
"""

from decimal import Decimal
from django.db.models import Q, Sum
from groups.models import GroupMembership
from expenses.models import Expense, ExpenseSplit
from settlements.models import Settlement


# =====================================================================
# SECTION 1: SETTLEMENT EXTENSION POINTS
# =====================================================================
# Why: Integrating the settlements app here allows net balances and
# breakdowns to correctly reflect direct payment transfers between users.
# =====================================================================

def _get_settlement_net(user, group, eligible_expense_ids):
    """
    Retrieves the net settlement contribution for a user's balance.

    Why: Settlement payments made by a user (paid_by == user) reduce their debt,
    representing a credit (positive). Payments received (paid_to == user) represent
    a debit (negative). Both must be restricted to dates within the user's
    membership window.

    Parameters:
        user: The User instance.
        group: The Group instance.
        eligible_expense_ids: Provided for consistency.

    Returns:
        Decimal: The net settlement contribution (credits - debits).
    """
    # Why: Retrieve the user's membership dates in the group to filter settlements.
    date_ranges = _get_membership_date_ranges(user, group)
    if not date_ranges:
        return Decimal('0.00')

    # Why: Filter to only include settlements that occurred during active membership windows.
    window_filter = Q()
    for joined_at, left_at in date_ranges:
        if left_at is None:
            window_filter |= Q(date__gte=joined_at)
        else:
            window_filter |= Q(date__gte=joined_at, date__lte=left_at)

    # Why: Sum of payments made by the user to others (credits).
    settlement_credit = Settlement.objects.filter(
        Q(group=group, paid_by=user) & window_filter
    ).aggregate(total=Sum('amount_inr'))['total'] or Decimal('0.00')

    # Why: Sum of payments received by the user from others (debits).
    settlement_debit = Settlement.objects.filter(
        Q(group=group, paid_to=user) & window_filter
    ).aggregate(total=Sum('amount_inr'))['total'] or Decimal('0.00')

    return settlement_credit - settlement_debit


def _get_settlement_rows(user, group, eligible_expense_ids):
    """
    Retrieves the list of settlement rows that compose a user's balance.

    Why: Provides line-by-line audit traceability in Rohan's drill-down breakdown.
    Each returned row represents a concrete Settlement record.

    Parameters:
        user: The User instance.
        group: The Group instance.
        eligible_expense_ids: Provided for consistency.

    Returns:
        list of dicts containing:
            - type: 'settlement_credit' (paid out) or 'settlement_debit' (received)
            - date: date
            - description: str (includes other member name)
            - amount: Decimal (signed)
            - record_id: int
            - record_model: 'Settlement'
    """
    date_ranges = _get_membership_date_ranges(user, group)
    if not date_ranges:
        return []

    window_filter = Q()
    for joined_at, left_at in date_ranges:
        if left_at is None:
            window_filter |= Q(date__gte=joined_at)
        else:
            window_filter |= Q(date__gte=joined_at, date__lte=left_at)

    # Why: Fetch all settlements involving the user within the membership windows.
    settlements = Settlement.objects.filter(
        Q(group=group) & (Q(paid_by=user) | Q(paid_to=user)) & window_filter
    ).select_related('paid_by', 'paid_to').order_by('date')

    rows = []
    for s in settlements:
        if s.paid_by == user:
            # Why: Payments made by the user are positive credit rows.
            rows.append({
                'type': 'settlement_credit',
                'date': s.date,
                'description': f"Settlement paid to {s.paid_to.name}",
                'amount': s.amount_inr,
                'record_id': s.id,
                'record_model': 'Settlement',
            })
        else:
            # Why: Payments received by the user are negative debit rows.
            rows.append({
                'type': 'settlement_debit',
                'date': s.date,
                'description': f"Settlement received from {s.paid_by.name}",
                'amount': -s.amount_inr,
                'record_id': s.id,
                'record_model': 'Settlement',
            })

    return rows


# =====================================================================
# SECTION 2: NET BALANCE CALCULATION
# =====================================================================
# Why: Computes a single user's net financial position within a group.
# This is the foundational calculation that all other functions build on.
# =====================================================================

def _get_membership_date_ranges(user, group):
    """
    Returns all membership date windows for a user in a group.

    Why: A user may have multiple historical membership periods in a group
    (e.g., joined Jan 1 - left Jan 15, re-joined Feb 1 - present).
    Each window defines the date range during which expenses count toward
    the user's balance. This centralizes the membership lookup so that
    balance calculations and breakdowns use identical scoping logic.

    Parameters:
        user: The User instance.
        group: The Group instance.

    Returns:
        list of tuples: [(joined_at, left_at), ...] where left_at is None
        for currently active memberships.
    """
    memberships = GroupMembership.objects.filter(
        user=user,
        group=group
    ).order_by('joined_at')

    return [(m.joined_at, m.left_at) for m in memberships]


def _get_eligible_expense_ids(group, date_ranges, as_of_date=None):
    """
    Returns IDs of ACTIVE expenses in the group that fall within
    at least one of the provided membership date ranges.

    Why: Expense eligibility is determined by two independent filters:
    1. The expense must be ACTIVE (not VOID or SUPERSEDED).
    2. The expense date must fall within at least one membership window.
    3. Optionally, the expense date must be <= as_of_date.

    Using expense IDs (rather than full objects) allows efficient
    downstream filtering via __in lookups on ExpenseSplit.

    Parameters:
        group: The Group instance.
        date_ranges: list of (joined_at, left_at) tuples from
            _get_membership_date_ranges().
        as_of_date: Optional date. If provided, only expenses with
            date <= as_of_date are included.

    Returns:
        QuerySet of Expense IDs (flat list via values_list).
    """
    if not date_ranges:
        return Expense.objects.none().values_list('id', flat=True)

    # Why: Build a Q filter that matches expense.date within ANY membership window.
    # Each window contributes an OR clause: joined_at <= date AND (left_at >= date OR left_at IS NULL).
    window_filter = Q()
    for joined_at, left_at in date_ranges:
        if left_at is None:
            # Why: Active membership — no upper bound on expense date.
            window_filter |= Q(date__gte=joined_at)
        else:
            # Why: Historical membership — expense date must be within [joined_at, left_at].
            window_filter |= Q(date__gte=joined_at, date__lte=left_at)

    # Why: Base filter restricts to the specific group and ACTIVE status only.
    base_filter = Q(group=group, status='ACTIVE')

    # Why: Optional upper-bound date filter for point-in-time balance queries.
    if as_of_date is not None:
        base_filter &= Q(date__lte=as_of_date)

    return Expense.objects.filter(
        base_filter & window_filter
    ).values_list('id', flat=True)


def get_user_net_balance(user, group, as_of_date=None):
    """
    Computes the net financial position of a user within a group.

    Why: This is the fundamental balance calculation. A user's net balance
    is the difference between what they paid for the group (credit) and
    what they owe the group (debit), plus any settlement adjustments.

    Calculation:
        credit = sum of ExpenseSplit.share_amount_inr for ACTIVE expenses
                 where expense.paid_by == user AND expense is within
                 the user's membership window(s)
        debit  = sum of ExpenseSplit.share_amount_inr for ACTIVE expenses
                 where split.user == user AND expense is within
                 the user's membership window(s)
        settlement_net = _get_settlement_net(user, group, eligible_ids)
        net_balance = credit - debit + settlement_net

    Sign Convention:
        Positive = user is owed money by the group (net creditor)
        Negative = user owes money to the group (net debtor)

    Parameters:
        user: The User instance.
        group: The Group instance.
        as_of_date: Optional date. If provided, only expenses with
            date <= as_of_date are included.

    Returns:
        Decimal: Signed net balance in INR.
    """
    # Step 1: Determine which expenses fall within the user's membership windows.
    date_ranges = _get_membership_date_ranges(user, group)
    eligible_ids = _get_eligible_expense_ids(group, date_ranges, as_of_date)

    # Step 2: Credit — total of all splits for expenses the user PAID FOR.
    # Why: When user pays for an expense, the sum of all splits equals
    # the total expense amount. This represents the credit extended by the user.
    credit = ExpenseSplit.objects.filter(
        expense_id__in=eligible_ids,
        expense__paid_by=user
    ).aggregate(
        total=Sum('share_amount_inr')
    )['total'] or Decimal('0.00')

    # Step 3: Debit — total of all splits where the user IS the debtor.
    # Why: Each split assigned to the user represents their obligation
    # toward a specific expense, regardless of who paid for it.
    debit = ExpenseSplit.objects.filter(
        expense_id__in=eligible_ids,
        user=user
    ).aggregate(
        total=Sum('share_amount_inr')
    )['total'] or Decimal('0.00')

    # Step 4: Settlement adjustment (extension point — currently returns 0).
    settlement_net = _get_settlement_net(user, group, eligible_ids)

    return credit - debit + settlement_net


# =====================================================================
# SECTION 3: GROUP BALANCES
# =====================================================================
# Why: Aggregates individual net balances for all members who have ever
# been part of the group. Historical members are included because they
# may still have outstanding balances from their active period.
# =====================================================================

def get_group_balances(group):
    """
    Returns the net balance for every member (current and historical)
    of a group.

    Why: Provides a complete financial snapshot of the group. Including
    historical members ensures that users who left with outstanding
    debts or credits are still visible in the ledger.

    Parameters:
        group: The Group instance.

    Returns:
        dict: {User instance: Decimal net balance} for every user
        who has ever held a membership in the group.
    """
    # Why: Fetching distinct users who have ever been members ensures
    # no one with an outstanding balance is missed.
    member_user_ids = GroupMembership.objects.filter(
        group=group
    ).values_list('user_id', flat=True).distinct()

    from django.contrib.auth import get_user_model
    User = get_user_model()
    members = User.objects.filter(id__in=member_user_ids)

    balances = {}
    for member in members:
        balances[member] = get_user_net_balance(member, group)

    return balances


# =====================================================================
# SECTION 4: DEBT SIMPLIFICATION
# =====================================================================
# Why: Reduces the number of payment transactions needed to settle all
# outstanding balances. See module docstring for full algorithm description.
# =====================================================================

def simplify_debts(group):
    """
    Implements a greedy debt-simplification algorithm to minimize the
    number of settlement transactions needed within a group.

    Why: In a group of N members, there could be up to N*(N-1)/2
    bilateral debts. This algorithm reduces that to at most N-1
    transactions by computing net positions and matching creditors
    with debtors greedily.

    Algorithm:
        1. Compute net balance for every member.
        2. Separate into creditors (positive) and debtors (negative).
        3. Sort creditors descending, debtors by abs(balance) descending.
        4. Match largest creditor with largest debtor, transfer
           min(creditor_balance, abs(debtor_balance)).
        5. Repeat until all balances are settled.

    Invariants (enforced by design):
        - Total money is preserved: sum(transaction amounts) == sum(positive balances)
        - No money is created: every transaction amount <= original balance of both parties
        - No money is destroyed: after all transactions, all net positions are zero

    Parameters:
        group: The Group instance.

    Returns:
        list of tuples: [(from_user, to_user, amount), ...]
        where from_user pays to_user the specified amount in INR.
        Returns empty list if all balances are zero.
    """
    balances = get_group_balances(group)

    # Why: Separate members into creditors and debtors based on their
    # net position. Members with zero balance need no action.
    creditors = []  # (user, positive_balance) — they are owed money
    debtors = []    # (user, negative_balance) — they owe money

    for user, balance in balances.items():
        if balance > Decimal('0.00'):
            creditors.append([user, balance])
        elif balance < Decimal('0.00'):
            debtors.append([user, balance])
        # Why: Users with zero balance are excluded — no action needed.

    # Why: Sorting ensures the greedy algorithm matches the largest
    # outstanding amounts first, which tends to minimize transaction count.
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1])  # Most negative first

    transactions = []
    ci = 0  # Creditor index
    di = 0  # Debtor index

    # Why: The greedy loop matches one creditor with one debtor at a time.
    # The transfer amount is the minimum of the creditor's remaining
    # balance and the debtor's remaining debt (absolute value).
    while ci < len(creditors) and di < len(debtors):
        creditor_user, creditor_balance = creditors[ci]
        debtor_user, debtor_balance = debtors[di]

        # Why: Transfer amount is the smaller of what's owed and what's due.
        transfer = min(creditor_balance, abs(debtor_balance))

        if transfer > Decimal('0.00'):
            # Why: Record the transaction as (payer, payee, amount).
            # The debtor pays the creditor.
            transactions.append((debtor_user, creditor_user, transfer))

        # Why: Reduce both sides by the transfer amount.
        creditors[ci][1] -= transfer
        debtors[di][1] += transfer  # Adding to a negative number moves toward zero

        # Why: Move to next creditor/debtor if their balance is fully settled.
        if creditors[ci][1] == Decimal('0.00'):
            ci += 1
        if debtors[di][1] == Decimal('0.00'):
            di += 1

    return transactions


# =====================================================================
# SECTION 5: BALANCE BREAKDOWN
# =====================================================================
# Why: Provides a traceable, line-by-line audit of every ExpenseSplit
# and Settlement that contributes to a user's net balance. This
# enables drill-down from a summary number to individual records.
# =====================================================================

def get_balance_breakdown(user, group):
    """
    Returns the complete list of ExpenseSplit and Settlement rows that
    compose a user's balance, with signed amounts and full traceability.

    Why: Enables Rohan's drill-down requirement — every cent of a user's
    balance must be traceable to a specific expense split or settlement
    record. Each row includes the record type, date, description, signed
    amount, and primary key for direct database lookup.

    Row Types:
        - 'expense_credit': User paid for this expense. Amount is positive
          (sum of all splits for that expense = total expense amount).
        - 'expense_debit': User's split share for an expense. Amount is
          negative (the user's obligation).
        - 'settlement_credit': User paid a settlement. Amount is positive.
          (Extension point — currently not populated.)
        - 'settlement_debit': User received a settlement. Amount is negative.
          (Extension point — currently not populated.)

    Parameters:
        user: The User instance.
        group: The Group instance.

    Returns:
        list of dicts, each containing:
            - type: str ('expense_credit', 'expense_debit',
                        'settlement_credit', 'settlement_debit')
            - date: date
            - description: str
            - amount: Decimal (signed: positive for credits, negative for debits)
            - record_id: int (ExpenseSplit PK or Settlement PK)
            - record_model: str ('ExpenseSplit' or 'Settlement')
            - expense_id: int (parent Expense PK, for expense rows only)
        Sorted by date ascending, then by type (credits before debits).
    """
    # Step 1: Get eligible expenses within membership windows.
    date_ranges = _get_membership_date_ranges(user, group)
    eligible_ids = _get_eligible_expense_ids(group, date_ranges)

    rows = []

    # Step 2: Credit rows — expenses the user paid for.
    # Why: For each expense the user paid, we create one credit row per split.
    # The sum of these split amounts equals the total expense amount,
    # representing the full credit the user extended to the group.
    credit_splits = ExpenseSplit.objects.filter(
        expense_id__in=eligible_ids,
        expense__paid_by=user
    ).select_related('expense', 'user')

    # Why: Group credit splits by expense to create one credit row per expense
    # (showing the total amount paid), rather than one row per split.
    credit_by_expense = {}
    for split in credit_splits:
        exp_id = split.expense_id
        if exp_id not in credit_by_expense:
            credit_by_expense[exp_id] = {
                'expense': split.expense,
                'total': Decimal('0.00'),
            }
        credit_by_expense[exp_id]['total'] += split.share_amount_inr

    for exp_id, data in credit_by_expense.items():
        rows.append({
            'type': 'expense_credit',
            'date': data['expense'].date,
            'description': f"Paid: {data['expense'].description}",
            'amount': data['total'],
            'record_id': exp_id,
            'record_model': 'Expense',
            'expense_id': exp_id,
        })

    # Step 3: Debit rows — the user's own split shares.
    # Why: Each split assigned to the user is an individual debit row,
    # providing line-by-line traceability of what the user owes.
    debit_splits = ExpenseSplit.objects.filter(
        expense_id__in=eligible_ids,
        user=user
    ).select_related('expense')

    for split in debit_splits:
        rows.append({
            'type': 'expense_debit',
            'date': split.expense.date,
            'description': f"Share: {split.expense.description}",
            'amount': -split.share_amount_inr,
            'record_id': split.id,
            'record_model': 'ExpenseSplit',
            'expense_id': split.expense_id,
        })

    # Step 4: Settlement rows (extension point — currently empty).
    settlement_rows = _get_settlement_rows(user, group, eligible_ids)
    rows.extend(settlement_rows)

    # Why: Sort by date ascending, then credits before debits for readability.
    type_order = {
        'expense_credit': 0,
        'settlement_credit': 1,
        'expense_debit': 2,
        'settlement_debit': 3,
    }
    rows.sort(key=lambda r: (r['date'], type_order.get(r['type'], 99)))

    return rows
