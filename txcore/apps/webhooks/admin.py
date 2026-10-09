from django.contrib import admin
from .models import WebhookEvent


@admin.register(WebhookEvent)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "status", "transaction_reference", "retry_count", "last_error")
    list_filter = ("provider", "status")
    readonly_fields = tuple(field.name for field in WebhookEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
