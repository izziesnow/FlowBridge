"""Load synthetic data into an empty database, for a hosted test copy of Flowbridge.

Run at every start-up of a hosted copy (deploy/render-start.sh). It does nothing once
the database holds any account, so testers' work survives restarts and redeploys.

    HOSTED_DATASET=demo          the small PAY demonstration project (default)
    HOSTED_DATASET=evaluation    the 120-request ZTL evaluation dataset
    HOSTED_PASSWORD=...          password for every synthetic account (optional)
"""
import os
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.approvals.management.commands.seed_demo import PASSWORD as DEMO_PASSWORD
from apps.evaluation.system import DEFAULT_PASSWORD as EVALUATION_PASSWORD


class Command(BaseCommand):
    help = "Load the demo or evaluation dataset if, and only if, the database has no accounts yet."

    def handle(self, *args, **options):
        if get_user_model().objects.exists():
            self.stdout.write("Accounts already exist; leaving the data as it is.")
            return
        dataset = os.environ.get("HOSTED_DATASET", "demo").strip().lower() or "demo"
        password = os.environ.get("HOSTED_PASSWORD", "").strip()
        if dataset == "demo":
            # The loaders' own messages include the password, so they are kept out of the platform's logs.
            call_command("seed_demo", password=password or DEMO_PASSWORD, verbosity=0, stdout=StringIO())
        elif dataset == "evaluation":
            # The baseline files go to a scratch folder: testers of the hosted copy only use the system.
            call_command("generate_evaluation_data", load=True, password=password or EVALUATION_PASSWORD,
                         out=tempfile.mkdtemp(prefix="flowbridge-eval-"), verbosity=0, stdout=StringIO())
        else:
            raise CommandError(f"HOSTED_DATASET must be 'demo' or 'evaluation', not {dataset!r}.")
        self.stdout.write(self.style.SUCCESS(f"Loaded the {dataset} dataset."))
