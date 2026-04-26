"""
Seed script - creates merchants with credit history for testing.
Run with: python seed.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from payouts.models import Merchant, LedgerEntry

def seed():
    print("Seeding database...")

    # Clear existing data
    LedgerEntry.objects.all().delete()
    Merchant.objects.all().delete()

    # Create 3 merchants
    merchant1 = Merchant.objects.create(
        name="Rahul Sharma - Freelance Designer",
        email="rahul@example.com",
        bank_account_number="1234567890",
        bank_ifsc="HDFC0001234"
    )

    merchant2 = Merchant.objects.create(
        name="Priya Singh - Digital Agency",
        email="priya@example.com",
        bank_account_number="0987654321",
        bank_ifsc="ICIC0005678"
    )

    merchant3 = Merchant.objects.create(
        name="Arjun Mehta - Content Creator",
        email="arjun@example.com",
        bank_account_number="1122334455",
        bank_ifsc="SBIN0009012"
    )

    # Add credit history for merchant 1
    # 50,000 rupees = 5,000,000 paise
    LedgerEntry.objects.create(
        merchant=merchant1,
        amount=5000000,
        entry_type='credit',
        description='Payment from Client USA - Logo Design Project'
    )
    LedgerEntry.objects.create(
        merchant=merchant1,
        amount=2500000,
        entry_type='credit',
        description='Payment from Client UK - Website Redesign'
    )

    # Add credit history for merchant 2
    # 1,00,000 rupees = 10,000,000 paise
    LedgerEntry.objects.create(
        merchant=merchant2,
        amount=10000000,
        entry_type='credit',
        description='Payment from Client Canada - Social Media Campaign'
    )
    LedgerEntry.objects.create(
        merchant=merchant2,
        amount=7500000,
        entry_type='credit',
        description='Payment from Client Australia - SEO Project'
    )

    # Add credit history for merchant 3
    LedgerEntry.objects.create(
        merchant=merchant3,
        amount=3000000,
        entry_type='credit',
        description='Payment from Client Germany - Video Production'
    )

    print("✅ Created 3 merchants with credit history!")
    print(f"  Merchant 1: {merchant1.name} - Balance: ₹{merchant1.get_available_balance()/100:.2f}")
    print(f"  Merchant 2: {merchant2.name} - Balance: ₹{merchant2.get_available_balance()/100:.2f}")
    print(f"  Merchant 3: {merchant3.name} - Balance: ₹{merchant3.get_available_balance()/100:.2f}")
    print("\nDone! You can now test the API.")

if __name__ == '__main__':
    seed()
