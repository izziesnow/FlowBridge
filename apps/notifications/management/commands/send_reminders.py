"""Remind approvers about overdue stages. Run on a schedule (the Compose 'scheduler' service runs it every 15 minutes).

    python manage.py send_reminders            # send reminders now
    python manage.py send_reminders --dry-run  # list what would be sent; change nothing
"""
from django.core.management.base import BaseCommand

from apps.notifications.reminders import send_overdue_reminders


class Command(BaseCommand):
    help = "Send in-app reminders for overdue approval stages."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would be sent without sending it.")

    def handle(self, *args, dry_run=False, **options):
        run = send_overdue_reminders(dry_run=dry_run)
        verb = "Would remind" if dry_run else "Reminded"
        for reference, stage, approver, hours in run.reminded:
            self.stdout.write(f"{verb} {approver} about {reference} stage {stage} ({hours} h overdue)")
        self.stdout.write(self.style.SUCCESS(
            f"{run.overdue} overdue stage(s); {len(run.reminded)} reminder(s) {'due' if dry_run else 'sent'}."
        ))
