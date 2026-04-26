"""
Tests for Playto Pay Payout Engine.
"""
from django.test import TestCase
from rest_framework.test import APIClient
from payouts.models import Merchant, LedgerEntry, Payout, IdempotencyKey


def create_test_merchant(name="Test Merchant", balance_paise=10000):
    merchant = Merchant.objects.create(
        name=name,
        email=f"{name.replace(' ', '')}@test.com",
        bank_account_number="1234567890",
        bank_ifsc="HDFC0001234"
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        amount=balance_paise,
        entry_type='credit',
        description='Test credit'
    )
    return merchant


class IdempotencyTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.merchant = create_test_merchant(balance_paise=100000)

    def test_same_idempotency_key_creates_one_payout(self):
        """Same key twice = only 1 payout created"""
        headers = {
            "HTTP_MERCHANT_ID": str(self.merchant.id),
            "HTTP_IDEMPOTENCY_KEY": "test-idem-key-12345",
            "content_type": "application/json"
        }
        payload = {"amount_paise": 50000, "bank_account_id": "1234567890"}

        response1 = self.client.post("/api/v1/payouts/", payload, **headers)
        response2 = self.client.post("/api/v1/payouts/", payload, **headers)

        self.assertIn(response1.status_code, [200, 201])
        self.assertIn(response2.status_code, [200, 201])

        payout_count = Payout.objects.filter(merchant=self.merchant).count()
        self.assertEqual(payout_count, 1,
            f"Expected 1 payout but got {payout_count}. Idempotency broken!")

        self.assertEqual(response1.data['payout_id'], response2.data['payout_id'])
        print(f"✅ Idempotency test passed! Only 1 payout for 2 requests.")

    def test_different_keys_create_separate_payouts(self):
        """Different keys = 2 payouts created"""
        payload = {"amount_paise": 10000, "bank_account_id": "1234567890"}

        r1 = self.client.post("/api/v1/payouts/", payload,
            HTTP_MERCHANT_ID=str(self.merchant.id),
            HTTP_IDEMPOTENCY_KEY="key-001",
            content_type="application/json")

        r2 = self.client.post("/api/v1/payouts/", payload,
            HTTP_MERCHANT_ID=str(self.merchant.id),
            HTTP_IDEMPOTENCY_KEY="key-002",
            content_type="application/json")

        self.assertIn(r1.status_code, [200, 201])
        self.assertIn(r2.status_code, [200, 201])
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 2)
        print(f"✅ Different keys test passed!")


class ConcurrencyTest(TestCase):
    """
    Test overdraw protection.
    Merchant has 1000 rupees. Two requests for 600 each.
    First succeeds, second must be rejected.
    In production, SELECT FOR UPDATE prevents race conditions.
    """
    def setUp(self):
        self.client = APIClient()
        self.merchant = create_test_merchant(balance_paise=100000)

    def test_overdraw_protection(self):
        """Balance of 1000, two requests of 600 - only first succeeds"""
        response1 = self.client.post(
            "/api/v1/payouts/",
            {"amount_paise": 60000, "bank_account_id": "1234567890"},
            HTTP_MERCHANT_ID=str(self.merchant.id),
            HTTP_IDEMPOTENCY_KEY="key-001",
            content_type="application/json"
        )
        response2 = self.client.post(
            "/api/v1/payouts/",
            {"amount_paise": 60000, "bank_account_id": "1234567890"},
            HTTP_MERCHANT_ID=str(self.merchant.id),
            HTTP_IDEMPOTENCY_KEY="key-002",
            content_type="application/json"
        )

        print(f"   Request 1: {response1.status_code}")
        print(f"   Request 2: {response2.status_code} - {response2.data}")

        self.assertEqual(response1.status_code, 201, "First request should succeed!")
        self.assertEqual(response2.status_code, 400, "Second should fail - insufficient balance!")

        from django.db.models import Sum
        total = LedgerEntry.objects.filter(
            merchant=self.merchant
        ).aggregate(total=Sum('amount'))['total'] or 0

        self.assertGreaterEqual(total, 0, f"Balance negative! Money integrity violated!")
        print(f"✅ Overdraw protection passed! Balance: {total} paise (never negative)")


class StateMachineTest(TestCase):
    def setUp(self):
        self.merchant = create_test_merchant(balance_paise=100000)

    def test_illegal_transitions_blocked(self):
        payout = Payout.objects.create(
            merchant=self.merchant,
            amount_paise=10000,
            bank_account_id="1234567890",
            status='completed'
        )
        self.assertFalse(payout.can_transition_to('pending'))
        self.assertFalse(payout.can_transition_to('failed'))
        self.assertFalse(payout.can_transition_to('processing'))
        print("✅ Illegal transitions blocked!")

    def test_legal_transitions_allowed(self):
        payout = Payout.objects.create(
            merchant=self.merchant,
            amount_paise=10000,
            bank_account_id="1234567890",
            status='pending'
        )
        self.assertTrue(payout.can_transition_to('processing'))
        payout.status = 'processing'
        payout.save()
        self.assertTrue(payout.can_transition_to('completed'))
        print("✅ Legal transitions work!")
