"""Load synthetic demonstration data for the fictional Zenkora Technologies Limited (ZTL).

ZTL is not a real company. Every name, email address and document below is
synthetic. All records are created through WorkflowService, so the demo data
carry the same evidence and audit trail as real use would.

    python manage.py seed_demo           # load once into an empty database
    python manage.py seed_demo --flush   # wipe the database first, then load
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.approvals.models import Decision, StageTask
from apps.approvals.services import WorkflowService
from apps.audit.models import record
from apps.discussion.services import post_comment, post_project_message
from apps.projects.models import Membership, Project, Role

PASSWORD = "ztl-demo-2026"
DOMAIN = "ztl.example"  # .example is reserved (RFC 2606), so these addresses can never reach a real inbox

PEOPLE = [
    # key, full name, job title, admin?
    ("admin", "Tolulope Adeyemi", "IT administrator", True),
    ("chinedu.eze", "Chinedu Eze", "Project manager", False),
    ("aisha.bello", "Aisha Bello", "Software engineer", False),
    ("emeka.nwosu", "Emeka Nwosu", "Software engineer", False),
    ("funmilayo.ogunleye", "Funmilayo Ogunleye", "Technical lead", False),
    ("ibrahim.musa", "Ibrahim Musa", "Product owner", False),
    ("ngozi.obi", "Ngozi Obi", "Quality assurance analyst", False),
    ("bola.adekunle", "Bola Adekunle", "Project manager", False),
]

PAY_ROLES = {
    "chinedu.eze": Role.PM,
    "aisha.bello": Role.REQUESTER,
    "emeka.nwosu": Role.REQUESTER,
    "funmilayo.ogunleye": Role.APPROVER,
    "ibrahim.musa": Role.APPROVER,
    "ngozi.obi": Role.VIEWER,
}


def doc(name, text):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/markdown")


class Command(BaseCommand):
    help = "Load synthetic demo data for the fictional organisation ZTL."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Delete all data before loading the demo.")

    def handle(self, *args, flush=False, **options):
        User = get_user_model()
        if flush:
            # TRUNCATE (used by flush) does not fire the row-level immutability triggers.
            call_command("flush", interactive=False, verbosity=0)
        elif User.objects.filter(email=f"admin@{DOMAIN}").exists():
            raise CommandError("Demo data already loaded. Run with --flush to reload from scratch.")

        with transaction.atomic():
            self._load(User)

        self.stdout.write(self.style.SUCCESS(
            f"Demo data loaded for the fictional organisation ZTL. Sign in as admin@{DOMAIN} "
            f"(or any user, e.g. aisha.bello@{DOMAIN}) with password '{PASSWORD}'."
        ))

    def _load(self, User):
        u = {}
        for key, name, title, is_admin in PEOPLE:
            email = f"{key}@{DOMAIN}"
            if is_admin:
                u[key] = User.objects.create_superuser(email, PASSWORD, full_name=name, job_title=title)
            else:
                u[key] = User.objects.create_user(email, PASSWORD, full_name=name, job_title=title)
        admin = u["admin"]

        pay = Project.objects.create(
            code="PAY", name="Payments Gateway Upgrade", created_by=admin,
            description="Upgrade of a client's card and transfer payments gateway (fictional ZTL project).",
        )
        hrm = Project.objects.create(
            code="HRM", name="HR Mobile App", created_by=admin,
            description="Internal staff self-service app (fictional ZTL project). PAY members are not members here.",
        )
        record("project.created", "Project PAY created (demo data)", actor=admin, project=pay)
        record("project.created", "Project HRM created (demo data)", actor=admin, project=hrm)
        for key, role in PAY_ROLES.items():
            Membership.objects.create(project=pay, user=u[key], role=role, added_by=admin)
        Membership.objects.create(project=hrm, user=u["bola.adekunle"], role=Role.PM, added_by=admin)

        pm, tl, po = u["chinedu.eze"], u["funmilayo.ogunleye"], u["ibrahim.musa"]
        workflow = WorkflowService.create_workflow_version(pay, pm, "Standard software change")
        WorkflowService.add_stage(workflow, pm, "Project manager review", pm, 24)
        WorkflowService.add_stage(workflow, pm, "Technical lead review", tl, 48)
        WorkflowService.add_stage(workflow, pm, "Product owner sign-off", po, 48)
        WorkflowService.publish_workflow(workflow, pm)

        aisha, emeka = u["aisha.bello"], u["emeka.nwosu"]
        A, R, C = Decision.Outcome.APPROVE, Decision.Outcome.REJECT, Decision.Outcome.REQUEST_CHANGES
        approvers = [pm, tl, po]

        def new(requester, title, description, files):
            req = WorkflowService.create_request(pay, requester, title, description)
            for name, text in files:
                WorkflowService.add_document_version(req, requester, doc(name, text))
            return req

        def decide(req, stage, outcome, reason=""):
            WorkflowService.decide(req, approvers[stage - 1], outcome, reason)

        # PAY-001: approved through all three stages.
        r1 = new(aisha, "Add retry with back-off to transfer callbacks",
                 "Retry failed bank callbacks up to five times with exponential back-off.\n"
                 "Risk: low. Rollback: disable the feature flag.",
                 [("design-note.md", "# Callback retry design\nVersion 1.\n"),
                  ("test-plan.md", "# Test plan\nUnit and sandbox tests.\n")])
        WorkflowService.submit(r1, aisha)
        decide(r1, 1, A)
        decide(r1, 2, A, "Back-off parameters look sensible.")
        decide(r1, 3, A)

        # PAY-002: in review, waiting at stage 2 (technical lead).
        r2 = new(emeka, "Upgrade TLS library to the current LTS release",
                 "Move the gateway to the current long-term support TLS library.\n"
                 "Risk: medium. Rollback: redeploy the previous container image.",
                 [("upgrade-plan.md", "# TLS upgrade plan\nVersion 1.\n")])
        WorkflowService.submit(r2, emeka)
        decide(r2, 1, A)
        # Simulate the passage of time so the demo shows an overdue stage (the reminder job will flag it).
        StageTask.objects.filter(cycle__request=r2, status=StageTask.Status.ACTIVE).update(
            activated_at=timezone.now() - timedelta(hours=75), due_at=timezone.now() - timedelta(hours=27)
        )
        stage3 = StageTask.objects.get(cycle__request=r2, position=3)
        WorkflowService.reassign_stage(r2, pm, stage3, pm, "Ibrahim is on leave this week; I will sign off for him.")

        # PAY-003: changes requested in cycle 1, revised, then approved in cycle 2.
        r3 = new(aisha, "Daily settlement report export to CSV",
                 "Add a CSV export of the daily settlement report for the finance team.\n"
                 "Risk: low. Rollback: hide the export button.",
                 [("report-spec.md", "# Settlement export spec\nVersion 1: all columns.\n")])
        WorkflowService.submit(r3, aisha)
        post_comment(r3, tl, "Does the export include full card numbers? Finance only needs the last four digits.")
        post_comment(r3, aisha, "It currently includes the full PAN. I can mask it if that is acceptable.")
        decide(r3, 1, A)
        decide(r3, 2, C, "Mask card numbers in the export and state the retention period.")
        WorkflowService.add_document_version(
            r3, aisha, doc("report-spec.md", "# Settlement export spec\nVersion 2: card numbers masked; "
                                             "files kept for 30 days.\n"),
            document=r3.documents.get(name="report-spec"),
        )
        WorkflowService.resubmit(r3, aisha)
        post_comment(r3, aisha, "Revision 2 masks card numbers and keeps export files for 30 days.")
        decide(r3, 1, A)
        decide(r3, 2, A, "Masking confirmed.")
        decide(r3, 3, A)

        # PAY-004: rejected at the product owner stage.
        r4 = new(emeka, "Remove two-factor prompt for transfers under ₦5,000",
                 "Skip the second factor for low-value transfers to reduce drop-off.\n"
                 "Risk: high. Rollback: re-enable the prompt.",
                 [("proposal.md", "# Proposal\nLow-value transfer exemption.\n")])
        WorkflowService.submit(r4, emeka)
        decide(r4, 1, A)
        decide(r4, 2, A, "Technically feasible.")
        decide(r4, 3, R, "Conflicts with the client's security policy; not acceptable.")

        # PAY-005: changes requested, waiting for the requester.
        r5 = new(aisha, "Rate-limit the merchant onboarding API",
                 "Add per-merchant rate limits to the onboarding API.\n"
                 "Risk: medium. Rollback: raise limits via configuration.",
                 [("rate-limits.md", "# Proposed limits\n100 requests per minute.\n")])
        WorkflowService.submit(r5, aisha)
        decide(r5, 1, C, "Attach the load-test evidence for the proposed limits.")

        # PAY-006: draft, not yet submitted.
        new(emeka, "Switch error logging to structured JSON",
            "Emit gateway logs as structured JSON for the new log platform.",
            [("logging-change.md", "# Logging change\nDraft.\n")])

        post_project_message(pay, pm, "Release freeze starts on Friday. Please get change requests in by Wednesday.")
        post_project_message(pay, tl, "Noted. I will clear the review queue by Thursday.")
