"""Generate the evaluation datasets for the fictional organisation ZTL (Section 3.1.3).

    python manage.py generate_evaluation_data                    # files only, into ./evaluation
    python manage.py generate_evaluation_data --load --flush     # also load the system dataset (wipes the DB)
"""
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.accounts.models import User
from apps.evaluation.baseline import BaselineWriter
from apps.evaluation.privacy import check_folder
from apps.evaluation.groundtruth import write_accounts, write_ground_truth, write_scenario_sets, write_spec
from apps.evaluation.scenario import DEFAULT_REQUESTS, DEFAULT_SEED, build_scenario
from apps.evaluation.system import DEFAULT_PASSWORD, compare_with_system, load_system


class Command(BaseCommand):
    help = "Generate the ZTL evaluation datasets: baseline artefacts, ground truth, scenario sets and system data."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
        parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS)
        parser.add_argument("--out", default="evaluation", help="Folder for the generated files.")
        parser.add_argument("--load", action="store_true", help="Load the system dataset into the database.")
        parser.add_argument("--flush", action="store_true", help="Delete all data first (required with --load "
                                                                 "unless the database is empty).")
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for every generated account.")

    def handle(self, *args, seed, requests, out, load, flush, password, **options):
        if requests < 60 or requests % 6:
            raise CommandError("--requests must be a multiple of 6 and at least 60.")
        scenario = build_scenario(seed=seed, total=requests)
        out_dir = Path(out)

        realisation = BaselineWriter(scenario, out_dir).write()
        fingerprint = write_ground_truth(scenario, realisation, out_dir)
        write_scenario_sets(scenario, out_dir)
        write_accounts(scenario, out_dir)
        write_spec(scenario, out_dir, fingerprint, realisation)
        self.stdout.write(f"Files written to {out_dir.resolve()} (ground truth {fingerprint[:12]}…)")
        self.stdout.write(f"Patterns injected: {scenario.pattern_counts} of eligible {scenario.eligible_counts}")
        problems = check_folder(out_dir)
        if problems:
            for problem in problems[:20]:
                self.stderr.write(self.style.ERROR(problem))
            raise CommandError(f"Privacy check failed: {len(problems)} problem(s).")
        self.stdout.write("Privacy check passed: only ztl.example addresses; no phone or card numbers; "
                          "no real organisations named.")

        if load:
            if flush:
                call_command("flush", interactive=False, verbosity=0)
            elif User.objects.exists():
                raise CommandError("The database already has data. Add --flush to replace it.")
            load_system(scenario, password=password)
            problems = compare_with_system(scenario)
            if problems:
                for problem in problems:
                    self.stderr.write(self.style.ERROR(problem))
                raise CommandError("The loaded system data do not match the scenario.")
            with connection.cursor() as cursor:
                cursor.execute("ANALYZE")
            self.stdout.write(self.style.SUCCESS(
                f"System dataset loaded and checked against the scenario: {len(scenario.stories)} requests. "
                f"Every account's password is '{password}' (admin: admin@ztl.example)."
            ))
