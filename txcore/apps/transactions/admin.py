from django.contrib import admin
from .models import Transaction, OutboxEvent


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("reference", "amount", "currency", "status", "provider", "created_at")
    list_filter = ("status", "currency", "provider")
    search_fields = ("reference", "provider_reference")
    readonly_fields = tuple(field.name for field in Transaction._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OutboxEvent)
class OutboxAdmin(admin.ModelAdmin):
    list_display = ("event_key", "topic", "attempts", "published_at", "last_error")
    readonly_fields = tuple(field.name for field in OutboxEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
