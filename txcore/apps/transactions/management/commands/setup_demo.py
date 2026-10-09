"""Create a local staff workspace account; preserve an existing password."""

import os
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo account setup is restricted to DEBUG environments.")
        user, created = get_user_model().objects.get_or_create(
            username="demo.admin",
            defaults={"email": "demo@txcore.local", "is_staff": True},
        )
        if created:
            user.set_password(os.environ.get("TXCORE_DEMO_PASSWORD", "TxCoreSandbox123!"))
            user.save()
        if user.is_staff:
            user.user_permissions.add(
                *Permission.objects.filter(
                    content_type__app_label__in=["transactions", "webhooks", "reconciliation"],
                    codename__startswith="view_",
                )
            )
        Token.objects.get_or_create(user=user)
        self.stdout.write("Workspace account ready: demo.admin (existing password preserved).")
