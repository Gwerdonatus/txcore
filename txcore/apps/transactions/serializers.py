from rest_framework import serializers
from .models import Transaction


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "amount",
            "currency",
            "description",
            "metadata",
            "provider",
        ]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


class TransactionResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id",
            "reference",
            "amount",
            "currency",
            "status",
            "description",
            "provider",
            "provider_reference",
            "metadata",
            "created_at",
            "updated_at",
            "settled_at",
        ]
        read_only_fields = fields
