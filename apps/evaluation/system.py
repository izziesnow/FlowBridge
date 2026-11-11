"""Load the scenario into Flowbridge: the system condition's dataset.

Every record is created through WorkflowService and the discussion service,
exactly as a user would create it, so the data carry the same evidence,
notifications and audit trail as real use. A simulated clock replays each
event at its scenario time, so dates, durations and overdue flags are
realistic. No immutability trigger is disabled to do this.
"""
from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone as django_timezone

from apps.accounts.models import User
from apps.approvals.models import ApprovalRequest, RequestState
from apps.approvals.services import WorkflowService
from apps.audit.models import record
from apps.discussion.services import post_comment
from apps.notifications.models import Notification
from apps.projects.models import Membership, Project, Role

from .scenario import DOMAIN, PROJECTS, STAGES

DEFAULT_PASSWORD = "ztl-eval-2026"


@contextmanager
def simulated_clock():
    """Patch django.utils.timezone.now so services and auto timestamps use scenario time."""
    state = {"now": None}
    real_now = django_timezone.now

    def now():
        return state["now"] or real_now()

    with mock.patch("django.utils.timezone.now", now):
        yield state


def _events(scenario):
    """Every action in every story, as (time, order, story, kind, payload), in time order."""
    events = []
    for story in scenario.stories:
        seq = 0

        def add(at, kind, payload=None):
            nonlocal seq
            events.append((at, story.project, story.number, seq, story, kind, payload))
            seq += 1

        add(story.raised_at, "create")
        for version in story.versions:
            add(version.at, "upload", version)
        for cycle in story.cycles:
            if cycle.number > 1 and story.revised_description:
                add(cycle.submitted_at - timedelta(seconds=30), "edit")
            add(cycle.submitted_at, "submit" if cycle.number == 1 else "resubmit", cycle)
            for decision in cycle.decisions:
                add(decision.at, "decide", decision)
        for author, text, at in story.comments:
            add(at, "comment", (author, text))
        if story.withdrawn:
            add(story.withdrawn[2], "withdraw", story.withdrawn)
    events.sort(key=lambda e: (e[0], e[1], e[2], e[3]))
    return events


@transaction.atomic
def load_system(scenario, password=DEFAULT_PASSWORD):
    with simulated_clock() as clock:
        clock["now"] = scenario.anchor - timedelta(days=160)
        admin = User.objects.create_superuser(f"admin@{DOMAIN}", password, full_name="Tolulope Adeyemi",
                                              job_title="IT administrator (ZTL-000)")
        users = {
            key: User.objects.create_user(p.email, password, full_name=p.name, job_title=f"{p.title} ({p.code})")
            for key, p in scenario.people.items()
        }
        projects = {}
        for code, name, description in PROJECTS:
            project = Project.objects.create(code=code, name=name, created_by=admin,
                                             description=f"{description} (fictional ZTL project).")
            projects[code] = project
            record("project.created", f"Project {code} created (evaluation dataset)", actor=admin, project=project)
            r = scenario.roles[code]
            members = [(r["pm"], Role.PM), (r["tl"], Role.APPROVER), (r["po"], Role.APPROVER)]
            members += [(k, Role.REQUESTER) for k in r["requesters"]] + [(k, Role.VIEWER) for k in r["viewers"]]
            for key, role in members:
                Membership.objects.create(project=project, user=users[key], role=role, added_by=admin)
            pm = users[r["pm"]]
            workflow = WorkflowService.create_workflow_version(project, pm, "Standard software change")
            for name_, role_key, due in STAGES:
                WorkflowService.add_stage(workflow, pm, name_, users[r[role_key]], due)
            WorkflowService.publish_workflow(workflow, pm)

        requests = {}
        for at, _, _, _, story, kind, payload in _events(scenario):
            clock["now"] = at
            key = (story.project, story.number)
            if kind == "create":
                req = WorkflowService.create_request(projects[story.project], users[story.requester], story.title,
                                                     story.description)
                assert req.number == story.number, (story.ref, req.number)
                requests[key] = req
                continue
            req = ApprovalRequest.objects.get(pk=requests[key].pk)
            if kind == "upload":
                upload = SimpleUploadedFile(payload.filename, payload.content, content_type="text/markdown")
                version = WorkflowService.add_document_version(req, users[story.requester], upload, name=payload.doc)
                assert version.number == payload.number and version.sha256 == payload.sha256, story.ref
            elif kind == "edit":
                WorkflowService.update_content(req, users[story.requester], req.title, story.revised_description)
            elif kind == "submit":
                WorkflowService.submit(req, users[story.requester])
            elif kind == "resubmit":
                WorkflowService.resubmit(req, users[story.requester])
            elif kind == "decide":
                WorkflowService.decide(req, users[payload.approver], payload.outcome, payload.reason)
            elif kind == "comment":
                post_comment(req, users[payload[0]], payload[1])
            elif kind == "withdraw":
                WorkflowService.withdraw(req, users[payload[0]], payload[1])

        # People have read everything except the last two days of notifications.
        Notification.objects.filter(created_at__lt=scenario.anchor - timedelta(days=2)).update(
            read_at=scenario.anchor - timedelta(days=2))
    return requests


def compare_with_system(scenario):
    """Return a list of differences between the scenario and the loaded database (empty when they agree)."""
    problems = []
    loaded = {r.reference: r for r in ApprovalRequest.objects.select_related("project", "requester")}
    if len(loaded) != len(scenario.stories):
        problems.append(f"{len(loaded)} requests in the database, {len(scenario.stories)} in the scenario")
    for story in scenario.stories:
        req = loaded.get(story.ref)
        if req is None:
            problems.append(f"{story.ref} missing")
            continue
        if req.state != story.state:
            problems.append(f"{story.ref}: state {req.state}, expected {story.state}")
        if req.requester.email != scenario.person(story.requester).email:
            problems.append(f"{story.ref}: wrong requester")
        active = req.active_task()
        if story.state == RequestState.IN_REVIEW:
            cycle = story.cycles[-1]
            expected = scenario.roles[story.project][STAGES[cycle.waiting_stage - 1][1]]
            if active is None or active.position != cycle.waiting_stage or active.approver.email != scenario.person(expected).email:
                problems.append(f"{story.ref}: current stage or approver differs")
        for cycle in story.cycles:
            db_cycle = req.cycles.filter(number=cycle.number).first()
            if db_cycle is None:
                problems.append(f"{story.ref}: cycle {cycle.number} missing")
                continue
            reviewed = sorted(rd.document_version.sha256 for rd in db_cycle.revision.revision_documents.all())
            if reviewed != sorted(v.sha256 for v in cycle.docs):
                problems.append(f"{story.ref}: cycle {cycle.number} reviewed different document versions")
            decisions = [(t.position, t.decision.outcome, t.decision.reason) for t in
                         db_cycle.tasks.filter(decision__isnull=False).select_related("decision").order_by("position")]
            if decisions != [(d.stage, d.outcome, d.reason) for d in cycle.decisions]:
                problems.append(f"{story.ref}: cycle {cycle.number} decisions differ")
    return problems
