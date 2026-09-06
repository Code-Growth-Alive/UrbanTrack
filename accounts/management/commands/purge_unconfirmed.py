"""Delete accounts that never completed email confirmation within 24h."""

from django.core.management.base import BaseCommand

from accounts.email_confirmation import purge_expired_unconfirmed


class Command(BaseCommand):
    help = "Delete accounts still unconfirmed after the 24h confirmation window."

    def handle(self, *args, **options):
        deleted = purge_expired_unconfirmed()
        self.stdout.write(self.style.SUCCESS(f"deleted {deleted} unconfirmed account(s)"))
