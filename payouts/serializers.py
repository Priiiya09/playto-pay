from rest_framework import serializers
from .models import Merchant, LedgerEntry, Payout


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ['id', 'amount', 'entry_type', 'description', 'created_at']


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = ['id', 'amount_paise', 'bank_account_id', 'status', 'attempts', 'created_at', 'updated_at']


class MerchantBalanceSerializer(serializers.ModelSerializer):
    available_balance = serializers.SerializerMethodField()
    held_balance = serializers.SerializerMethodField()
    recent_entries = serializers.SerializerMethodField()
    payouts = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = ['id', 'name', 'email', 'bank_account_number', 'bank_ifsc', 'available_balance', 'held_balance', 'recent_entries', 'payouts']

    def get_available_balance(self, obj):
        return obj.get_available_balance()

    def get_held_balance(self, obj):
        return obj.get_held_balance()

    def get_recent_entries(self, obj):
        entries = obj.ledger_entries.all()[:10]
        return LedgerEntrySerializer(entries, many=True).data

    def get_payouts(self, obj):
        payouts = obj.payouts.all()[:10]
        return PayoutSerializer(payouts, many=True).data


class PayoutRequestSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=1)
    bank_account_id = serializers.CharField(max_length=100)

    def validate_amount_paise(self, value):
        # Minimum payout is 100 paise = 1 rupee
        if value < 100:
            raise serializers.ValidationError("Minimum payout is 100 paise (1 rupee)")
        return value
