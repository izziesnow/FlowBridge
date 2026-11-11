"""Check that the evidence store is intact. Used after a restore (NFR08) and in the CI smoke test.

Checks:
1. every document version's file exists and still matches its SHA-256 checksum;
2. the immutability trigger is installed on every evidence table;
3. workflow state is consistent: a request in review has exactly one open
   cycle and one active stage, and no other request has an active stage;
4. every completed stage has a decision made by that stage's approver;
5. each request's current revision is its latest revision.

Exits with status 1 if any check fails.
"""
import hashlib

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, F, Max, Q

from apps.approvals.models import ApprovalRequest, Decision, DocumentVersion, RequestState, StageTask

IMMUTABLE_TABLES = [
    "approvals_revision", "approvals_revisiondocument", "approvals_documentversion", "approvals_decision",
    "approvals_reassignment", "audit_auditevent", "discussion_comment", "discussion_projectmessage",
]


class Command(BaseCommand):
    help = "Verify document checksums, immutability triggers and workflow consistency."

    def handle(self, *args, **options):
        problems = []

        checked = 0
        for version in DocumentVersion.objects.select_related("document__request__project").iterator():
            checked += 1
            label = f"{version.document.request.reference} '{version.document.name}' v{version.number}"
            try:
                digest = hashlib.sha256()
                with version.file.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(64 * 1024), b""):
                        digest.update(chunk)
            except FileNotFoundError:
                problems.append(f"Missing file for {label}")
                continue
            if digest.hexdigest() != version.sha256:
                problems.append(f"Checksum mismatch for {label}")
        self.stdout.write(f"Document versions checked: {checked}")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE NOT t.tgisinternal AND t.tgname LIKE %s AND t.tgenabled <> 'D'",
                ["%_immutable"],
            )
            protected = {row[0] for row in cursor.fetchall()}
        for table in IMMUTABLE_TABLES:
            if table not in protected:
                problems.append(f"Immutability trigger missing or disabled on {table}")
        self.stdout.write(f"Immutable tables protected: {len(set(IMMUTABLE_TABLES) & protected)}/{len(IMMUTABLE_TABLES)}")

        requests = ApprovalRequest.objects.annotate(
            open_cycles=Count("cycles", filter=Q(cycles__ended_at__isnull=True), distinct=True),
            active_tasks=Count("cycles__tasks", filter=Q(cycles__tasks__status=StageTask.Status.ACTIVE), distinct=True),
            latest_revision=Max("revisions__number"),
        ).select_related("project", "current_revision")
        for r in requests:
            if r.state == RequestState.IN_REVIEW and (r.open_cycles != 1 or r.active_tasks != 1):
                problems.append(f"{r.reference} is in review but has {r.open_cycles} open cycle(s) "
                                f"and {r.active_tasks} active stage(s)")
            if r.state != RequestState.IN_REVIEW and (r.open_cycles or r.active_tasks):
                problems.append(f"{r.reference} is {r.get_state_display().lower()} but still has an open cycle")
            if r.current_revision and r.current_revision.number != r.latest_revision:
                problems.append(f"{r.reference} does not point at its latest revision")
        self.stdout.write(f"Requests checked: {requests.count()}")

        undecided = StageTask.objects.filter(status=StageTask.Status.COMPLETED, decision__isnull=True)
        for task in undecided.select_related("cycle__request__project"):
            problems.append(f"{task.cycle.request.reference} stage {task.position} is completed without a decision")
        for decision in Decision.objects.select_related("task__cycle__request__project").exclude(
            actor=F("task__approver")
        ):
            problems.append(f"{decision.task.cycle.request.reference} stage {decision.task.position}: "
                            f"decision not made by the stage's approver")
        self.stdout.write(f"Decisions checked: {Decision.objects.count()}")

        if problems:
            for problem in problems:
                self.stderr.write(self.style.ERROR(f"FAIL  {problem}"))
            raise CommandError(f"Integrity check failed: {len(problems)} problem(s).")
        self.stdout.write(self.style.SUCCESS("Integrity check passed."))
