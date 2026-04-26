import random
import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import Payout, LedgerEntry

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_payout(self, payout_id):
    """
    Background worker that processes a pending payout.
    
    Simulates bank settlement:
    - 70% success
    - 20% failure  
    - 10% hangs in processing (will be retried)
    
    Retry logic: exponential backoff, max 3 attempts
    """
    logger.info(f"Processing payout {payout_id}, attempt {self.request.retries + 1}")

    try:
        with transaction.atomic():
            # Lock the payout row while we process it
            payout = Payout.objects.select_for_update().get(id=payout_id)

            # Only process pending payouts
            if payout.status != 'pending':
                logger.info(f"Payout {payout_id} is already {payout.status}, skipping")
                return

            # Move to processing state
            if not payout.can_transition_to('processing'):
                logger.error(f"Cannot transition payout {payout_id} to processing")
                return

            payout.status = 'processing'
            payout.attempts += 1
            payout.save(update_fields=['status', 'attempts', 'updated_at'])

    except Payout.DoesNotExist:
        logger.error(f"Payout {payout_id} not found")
        return

    # Simulate bank processing delay (outside transaction)
    # 70% success, 20% failure, 10% hang
    outcome = random.random()

    if outcome < 0.70:
        # SUCCESS - 70% chance
        _complete_payout(payout_id)

    elif outcome < 0.90:
        # FAILURE - 20% chance
        _fail_payout(payout_id)

    else:
        # HANG - 10% chance - retry with exponential backoff
        logger.warning(f"Payout {payout_id} is hanging, will retry")
        try:
            # Exponential backoff: 30s, 60s, 120s
            countdown = 30 * (2 ** self.request.retries)
            raise self.retry(countdown=countdown)
        except self.MaxRetriesExceededError:
            # Max retries exceeded, mark as failed
            logger.error(f"Payout {payout_id} exceeded max retries, marking as failed")
            _fail_payout(payout_id)


def _complete_payout(payout_id):
    """
    Mark payout as completed.
    The debit ledger entry was already created when payout was requested.
    So no new ledger entry needed - balance is already reduced.
    """
    try:
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(id=payout_id)

            if not payout.can_transition_to('completed'):
                logger.error(f"Cannot complete payout {payout_id}, current status: {payout.status}")
                return

            payout.status = 'completed'
            payout.save(update_fields=['status', 'updated_at'])

            logger.info(f"Payout {payout_id} completed successfully!")

    except Payout.DoesNotExist:
        logger.error(f"Payout {payout_id} not found during completion")


def _fail_payout(payout_id):
    """
    Mark payout as failed AND return funds to merchant.
    Both operations happen in ONE atomic transaction.
    This is critical - we cannot fail without returning funds.
    """
    try:
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(id=payout_id)

            if not payout.can_transition_to('failed'):
                logger.error(f"Cannot fail payout {payout_id}, current status: {payout.status}")
                return

            # Mark as failed
            payout.status = 'failed'
            payout.save(update_fields=['status', 'updated_at'])

            # Return funds to merchant - create a CREDIT entry
            # This atomically reverses the debit that was created earlier
            LedgerEntry.objects.create(
                merchant=payout.merchant,
                amount=payout.amount_paise,   # Positive = credit back
                entry_type='credit',
                description=f'Payout #{payout_id} failed - funds returned',
                payout=payout
            )

            logger.info(f"Payout {payout_id} failed, {payout.amount_paise} paise returned to merchant")

    except Payout.DoesNotExist:
        logger.error(f"Payout {payout_id} not found during failure handling")


@shared_task
def retry_stuck_payouts():
    """
    Finds payouts stuck in 'processing' for more than 30 seconds
    and retries them. This runs periodically.
    """
    stuck_time = timezone.now() - timedelta(seconds=30)

    stuck_payouts = Payout.objects.filter(
        status='processing',
        updated_at__lte=stuck_time,
        attempts__lt=3
    )

    for payout in stuck_payouts:
        logger.warning(f"Found stuck payout {payout.id}, retrying...")
        process_payout.apply_async(args=[payout.id])

    logger.info(f"Found and retried {stuck_payouts.count()} stuck payouts")
