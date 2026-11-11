"""Send notification emails that are waiting or that failed earlier (FR13). Run by the scheduler."""
from django.core.management.base import BaseCommand

from apps.notifications.services import deliver_emails


class Command(BaseCommand):
    help = "Send pending notification emails and retry failed ones."

    def handle(self, *args, **options):
        sent, failed = deliver_emails()
        self.stdout.write(self.style.SUCCESS(f"{sent} email(s) sent; {failed} failed and will be retried."))
