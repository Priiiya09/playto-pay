from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Merchant, LedgerEntry, Payout, IdempotencyKey
from .serializers import MerchantBalanceSerializer, PayoutRequestSerializer, PayoutSerializer


class MerchantBalanceView(APIView):
    """
    GET /api/v1/merchants/<merchant_id>/balance
    Returns merchant balance, held balance, recent entries and payouts
    """
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = MerchantBalanceSerializer(merchant)
        return Response(serializer.data)


class MerchantListView(APIView):
    """
    GET /api/v1/merchants
    Returns list of all merchants
    """
    def get(self, request):
        merchants = Merchant.objects.all()
        serializer = MerchantBalanceSerializer(merchants, many=True)
        return Response(serializer.data)


class PayoutCreateView(APIView):
    """
    POST /api/v1/payouts
    Creates a payout request with idempotency support.

    Headers required:
    - Idempotency-Key: <uuid>
    - Merchant-Id: <merchant_id>
    """
    def post(self, request):
        # Step 1: Get merchant ID from header
        merchant_id = request.headers.get('Merchant-Id')
        if not merchant_id:
            return Response({'error': 'Merchant-Id header required'}, status=status.HTTP_400_BAD_REQUEST)

        # Step 2: Get idempotency key from header
        idempotency_key = request.headers.get('Idempotency-Key')
        if not idempotency_key:
            return Response({'error': 'Idempotency-Key header required'}, status=status.HTTP_400_BAD_REQUEST)

        # Step 3: Get merchant
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=status.HTTP_404_NOT_FOUND)

        # Step 4: Check idempotency - have we seen this key before?
        expiry_time = timezone.now() - timedelta(hours=24)
        existing_key = IdempotencyKey.objects.filter(
            merchant=merchant,
            key=idempotency_key,
            created_at__gte=expiry_time  # Only keys less than 24 hours old
        ).first()

        if existing_key:
            # We have seen this key before! Return the EXACT same response
            return Response(existing_key.response_data, status=status.HTTP_200_OK)

        # Step 5: Validate request data
        serializer = PayoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount_paise = serializer.validated_data['amount_paise']
        bank_account_id = serializer.validated_data['bank_account_id']

        # Step 6: Create payout with database-level locking
        # This is the CRITICAL part that prevents race conditions
        try:
            with transaction.atomic():
                # Lock the merchant row so no other request can read/modify
                # balance at the same time. This is SELECT FOR UPDATE.
                merchant = Merchant.objects.select_for_update().get(id=merchant_id)

                # Calculate available balance AT DATABASE LEVEL
                available_balance = merchant.get_available_balance()
                held_balance = merchant.get_held_balance()
                actual_available = available_balance - held_balance

                # Check if merchant has enough balance
                if actual_available < amount_paise:
                    return Response({
                        'error': 'Insufficient balance',
                        'available_balance': actual_available,
                        'requested_amount': amount_paise
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Create the payout in pending state
                payout = Payout.objects.create(
                    merchant=merchant,
                    amount_paise=amount_paise,
                    bank_account_id=bank_account_id,
                    status='pending',
                    idempotency_key=idempotency_key
                )

                # Create a debit ledger entry to hold the funds
                LedgerEntry.objects.create(
                    merchant=merchant,
                    amount=-amount_paise,  # Negative = debit
                    entry_type='debit',
                    description=f'Payout request #{payout.id} - funds held',
                    payout=payout
                )

                # Build response
                response_data = {
                    'payout_id': payout.id,
                    'amount_paise': payout.amount_paise,
                    'status': payout.status,
                    'bank_account_id': payout.bank_account_id,
                    'created_at': payout.created_at.isoformat(),
                    'message': 'Payout request created successfully'
                }

                # Save idempotency key with the response
                IdempotencyKey.objects.create(
                    merchant=merchant,
                    key=idempotency_key,
                    response_data=response_data
                )

                # Queue the background job to process this payout
                from .tasks import process_payout
                process_payout.apply_async(
                    args=[payout.id],
                    countdown=2  # Start after 2 seconds
                )

                return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PayoutDetailView(APIView):
    """
    GET /api/v1/payouts/<payout_id>
    Returns details of a specific payout
    """
    def get(self, request, payout_id):
        try:
            payout = Payout.objects.get(id=payout_id)
        except Payout.DoesNotExist:
            return Response({'error': 'Payout not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PayoutSerializer(payout)
        return Response(serializer.data)


class PayoutListView(APIView):
    """
    GET /api/v1/merchants/<merchant_id>/payouts
    Returns all payouts for a merchant
    """
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=status.HTTP_404_NOT_FOUND)

        payouts = merchant.payouts.all()
        serializer = PayoutSerializer(payouts, many=True)
        return Response(serializer.data)
