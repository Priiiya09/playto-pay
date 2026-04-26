# EXPLAINER.md

## 1. The Ledger

### Balance Calculation Query:

```python
def get_available_balance(self):
    result = self.ledger_entries.aggregate(
        total=Sum('amount')
    )
    return result['total'] or 0
```

### Why I modelled it this way:

Every money movement — whether a credit (customer pays merchant) or a debit (merchant withdraws) — is stored as a row in the `LedgerEntry` table. Credits are stored as positive integers, debits as negative integers, all in paise (never floats).

The balance is always derived by summing all ledger entries at the database level using `SUM()`. I never fetch rows into Python and add them up manually. This means:

- The database is always the single source of truth
- There is no "balance column" that can get out of sync
- If I want to audit, I can trace every rupee movement
- The invariant `SUM(ledger_entries) == displayed_balance` always holds

I used `BigIntegerField` for all amounts because floats cannot represent money precisely. For example, `0.1 + 0.2` in Python gives `0.30000000000000004`. Storing paise as integers eliminates this entirely.

---

## 2. The Lock

### Exact code that prevents overdraw:

```python
with transaction.atomic():
    # SELECT FOR UPDATE locks the merchant row
    # No other transaction can read or modify this row
    # until this transaction commits or rolls back
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)

    available_balance = merchant.get_available_balance()
    held_balance = merchant.get_held_balance()
    actual_available = available_balance - held_balance

    if actual_available < amount_paise:
        return Response({'error': 'Insufficient balance'}, status=400)

    # Safe to create payout here - balance is locked
    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(amount=-amount_paise, ...)
```

### The database primitive it relies on:

`SELECT FOR UPDATE` — a PostgreSQL row-level lock. When transaction A calls `select_for_update()` on a merchant row, transaction B trying to do the same must wait until A commits or rolls back. This means the check-then-deduct sequence is atomic. Two simultaneous 60-rupee requests on a 100-rupee balance cannot both pass the balance check — one will wait, see the updated balance, and be rejected.

This is database-level locking, not Python-level locking. Python threading locks (like `threading.Lock()`) would not protect against concurrent requests coming from separate processes or servers.

---

## 3. The Idempotency

### How the system knows it has seen a key before:

```python
existing_key = IdempotencyKey.objects.filter(
    merchant=merchant,
    key=idempotency_key,
    created_at__gte=expiry_time  # Only within 24 hours
).first()

if existing_key:
    return Response(existing_key.response_data, status=200)
```

The `IdempotencyKey` table stores the merchant, the key string, and the exact JSON response that was returned. Keys are scoped per merchant — the same UUID used by two different merchants is treated as two different keys. Keys expire after 24 hours.

### What happens if first request is in-flight when second arrives:

The `IdempotencyKey` record is created inside the same `transaction.atomic()` block as the payout. If the first request has not yet committed, the second request will not find an existing key and will try to create one too. However, the `unique_together = ['merchant', 'key']` constraint on the `IdempotencyKey` model means the database will raise an `IntegrityError` on the duplicate insert. This error is caught and the second request returns an appropriate error response. In production I would handle this more gracefully with a short retry or a locked key reservation pattern.

---

## 4. The State Machine

### Where failed-to-completed is blocked:

```python
# In models.py - Payout model
LEGAL_TRANSITIONS = {
    'pending': ['processing'],
    'processing': ['completed', 'failed'],
    'completed': [],   # Terminal - no transitions allowed
    'failed': [],      # Terminal - no transitions allowed
}

def can_transition_to(self, new_status):
    allowed = self.LEGAL_TRANSITIONS.get(self.status, [])
    return new_status in allowed

def transition_to(self, new_status):
    if not self.can_transition_to(new_status):
        raise ValueError(
            f"Illegal transition: {self.status} -> {new_status}"
        )
    self.status = new_status
    self.save(update_fields=['status', 'updated_at'])
```

Both `completed` and `failed` map to empty lists `[]`. So `can_transition_to('completed')` on a failed payout returns `False`. Any code trying to do `failed -> completed` will either get `False` or a `ValueError`. The Celery task checks `can_transition_to()` before every state change, so illegal transitions are blocked at the model level, not just the API level.

---

## 5. The AI Audit

### What AI gave me (wrong):

When I asked AI to write the balance check, it initially gave me this:

```python
# AI's wrong version
merchant = Merchant.objects.get(id=merchant_id)
balance = merchant.get_available_balance()  # fetches from DB
if balance >= amount_paise:
    payout = Payout.objects.create(...)  # race condition here!
```

### What was wrong:

There is no lock between the balance check and the payout creation. Two requests could both call `get()`, both read the same balance (say 10000 paise), both pass the `if` check, and both create a payout — overdrawing the merchant. This is a classic TOCTOU (Time of Check to Time of Use) race condition.

### What I replaced it with:

```python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    balance = merchant.get_available_balance()
    if balance >= amount_paise:
        payout = Payout.objects.create(...)
```

By wrapping in `transaction.atomic()` and using `select_for_update()`, the merchant row is locked for the duration of the transaction. The second concurrent request must wait at the `select_for_update()` call until the first transaction commits. When it gets the lock, it re-reads the balance (which is now lower) and correctly rejects the request.

AI also initially suggested using `DecimalField` for money amounts. I caught this and replaced it with `BigIntegerField` storing paise, because decimals in databases can still have precision issues and integer arithmetic is always exact.
