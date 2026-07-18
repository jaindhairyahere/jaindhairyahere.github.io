"""Card + cashback-program serializers.

Sensitive card data (last4/expiry) is write-only and encrypted on save;
it is never returned by the API.
"""
from rest_framework import serializers

from apps.cards.models import CashbackProgram, CreditCard, Wallet
from apps.members.models import Member


class WalletSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "group", "owner", "owner_name", "name", "coin_rate", "currency", "is_active"]

    def validate(self, attrs):
        group = attrs.get("group") or getattr(self.instance, "group", None)
        owner = attrs.get("owner") or getattr(self.instance, "owner", None)
        if group and owner and owner.group_id != group.id:
            raise serializers.ValidationError("Owner must be a member of the wallet's group.")
        return attrs


class CashbackProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashbackProgram
        fields = [
            "id", "card", "merchant", "percent", "currency", "is_active",
            "payout", "wallet", "coin_expiry_days",
            "max_per_txn", "cap_per_day", "cap_per_week", "cap_per_month",
            "cap_per_year", "cap_total", "max_vouches_total", "max_per_day",
            "max_per_week", "max_per_month", "max_per_year",
        ]

    def validate_percent(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Percent must be between 0 and 100.")
        return value

    def validate(self, attrs):
        payout = attrs.get("payout", getattr(self.instance, "payout", "cash"))
        wallet = attrs.get("wallet", getattr(self.instance, "wallet", None))
        if payout == "coins" and not wallet:
            raise serializers.ValidationError("Coin payout requires a wallet.")
        return attrs


class CreditCardSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)
    has_last4 = serializers.BooleanField(read_only=True)
    programs = CashbackProgramSerializer(many=True, read_only=True)

    # Write-only sensitive inputs (optional). Never echoed back.
    last4 = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=4)
    expiry = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=5)

    class Meta:
        model = CreditCard
        fields = [
            "id", "group", "owner", "owner_name", "display_name", "issuer",
            "network", "billing_cycle_day", "is_active", "has_last4",
            "programs", "last4", "expiry",
        ]

    def validate(self, attrs):
        group = attrs.get("group") or getattr(self.instance, "group", None)
        owner = attrs.get("owner") or getattr(self.instance, "owner", None)
        if group and owner and owner.group_id != group.id:
            raise serializers.ValidationError("Owner must be a member of the card's group.")
        return attrs

    def _apply_sensitive(self, instance, validated):
        if "last4" in validated:
            instance.last4_enc = validated.pop("last4") or None
        if "expiry" in validated:
            instance.expiry_enc = validated.pop("expiry") or None

    def create(self, validated_data):
        last4 = validated_data.pop("last4", None)
        expiry = validated_data.pop("expiry", None)
        instance = CreditCard(**validated_data)
        instance.last4_enc = last4 or None
        instance.expiry_enc = expiry or None
        instance.save()
        return instance

    def update(self, instance, validated_data):
        self._apply_sensitive(instance, validated_data)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance
