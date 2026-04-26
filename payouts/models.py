from django.db import models
from django.db.models import Sum


class Merchant(models.Model):
    """
    A merchant is a freelancer or agency using Playto Pay.
    They receive payments from international customers.
    """
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    bank_account_number = models.CharField(max_length=50)
    bank_ifsc = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_available_balance(self):
        """
        Available balance = total credits - total debits
        Calculated at DATABASE level using SUM, not Python arithmetic.
        This is important for money integrity.
        """
        result = self.ledger_entries.aggregate(
            total=Sum('amount')  # credits are positive, debits are negative
        )
        return result['total'] or 0

    def get_held_balance(self):
        """
        Held balance = sum of all PENDING payouts
        Money that is reserved but not yet processed
        """
        result = self.payouts.filter(
            status='pending'
        ).aggregate(
            total=Sum('amount_paise')
        )
        return result['total'] or 0

    def __str__(self):
        return f"{self.name} ({self.email})"

    class Meta:
        db_table = 'merchants'


class LedgerEntry(models.Model):
    """
    Every money movement is recorded here.
    Credits (money coming in) = positive amount
    Debits (money going out) = negative amount
    
    Balance = SUM of all entries for a merchant
    This is the SOURCE OF TRUTH for balance.
    """
    ENTRY_TYPES = [
        ('credit', 'Credit'),   # Customer paid merchant
        ('debit', 'Debit'),     # Merchant withdrew money
    ]

    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,  # Never delete merchant if entries exist
        related_name='ledger_entries'
    )
    amount = models.BigIntegerField()  # Always in paise, NEVER floats!
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES)
    description = models.CharField(max_length=255)
    payout = models.ForeignKey(
        'Payout',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='ledger_entries'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.entry_type}: {self.amount} paise for {self.merchant.name}"

    class Meta:
        db_table = 'ledger_entries'
        ordering = ['-created_at']


class IdempotencyKey(models.Model):
    """
    Stores idempotency keys to prevent duplicate payout requests.
    If same key is sent twice, return the same response.
    Keys expire after 24 hours.
    """
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name='idempotency_keys'
    )
    key = models.CharField(max_length=255)
    response_data = models.JSONField()  # Store the exact response to return again
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'idempotency_keys'
        unique_together = ['merchant', 'key']  # Key is unique PER merchant


class Payout(models.Model):
    """
    A payout request from a merchant to their bank account.
    
    State machine:
    pending -> processing -> completed
    pending -> processing -> failed
    
    NO other transitions allowed!
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),         # Just created, funds held
        ('processing', 'Processing'),   # Being processed by bank
        ('completed', 'Completed'),     # Money sent to bank successfully
        ('failed', 'Failed'),           # Failed, funds returned to merchant
    ]

    # Legal transitions - this is our state machine
    LEGAL_TRANSITIONS = {
        'pending': ['processing'],
        'processing': ['completed', 'failed'],
        'completed': [],   # Terminal state - no transitions allowed
        'failed': [],      # Terminal state - no transitions allowed
    }

    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name='payouts'
    )
    amount_paise = models.BigIntegerField()  # Always in paise, NEVER floats!
    bank_account_id = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    attempts = models.IntegerField(default=0)  # How many times we tried
    idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def can_transition_to(self, new_status):
        """
        Check if a status transition is legal.
        This is where failed->completed is BLOCKED.
        """
        allowed = self.LEGAL_TRANSITIONS.get(self.status, [])
        return new_status in allowed

    def transition_to(self, new_status):
        """
        Safely transition to a new status.
        Raises error if transition is illegal.
        """
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Illegal transition: {self.status} -> {new_status}. "
                f"Allowed: {self.LEGAL_TRANSITIONS.get(self.status, [])}"
            )
        self.status = new_status
        self.save(update_fields=['status', 'updated_at'])

    def __str__(self):
        return f"Payout {self.id}: {self.amount_paise} paise ({self.status})"

    class Meta:
        db_table = 'payouts'
        ordering = ['-created_at']
