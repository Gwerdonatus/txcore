from django.contrib import admin
from .models import ReconciliationRun, ReconciliationDiscrepancy


@admin.register(ReconciliationRun)
class RunAdmin(admin.ModelAdmin):
    list_display = ("filename", "status", "matched", "discrepancies", "created_at")
    readonly_fields = tuple(field.name for field in ReconciliationRun._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReconciliationDiscrepancy)
class DiscrepancyAdmin(admin.ModelAdmin):
    list_display = ("reference", "discrepancy_type", "resolved", "notes")
    readonly_fields = tuple(field.name for field in ReconciliationDiscrepancy._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
