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

    def validate(self, data):
        if data.get("provider") == "stripe":
            from txcore.providers.stripe import minor_units

            try:
                minor_units(data["amount"], data.get("currency", "USD"))
            except ValueError as exc:
                raise serializers.ValidationError(str(exc))
        return data

    def validate_provider(self, value):
        if value not in {"stripe", "demo"}:
            raise serializers.ValidationError("Choose stripe (sandbox) or demo (simulation).")
        return value

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
