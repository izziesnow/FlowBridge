"""History export (FR12): CSV files for the request register, the decision history and the audit log.

Cells that a spreadsheet would treat as a formula are prefixed with an
apostrophe, so an exported file cannot run a formula hidden in a title,
reason or comment (CSV injection; OWASP).
"""
import csv
import io
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Min, Prefetch
from django.utils import timezone

from apps.audit.models import AuditEvent

from .models import Decision, ReviewCycle, RevisionDocument

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S") if hasattr(value, "tzinfo") else value.isoformat()
    text = str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def to_csv(header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    count = 0
    for row in rows:
        writer.writerow([safe(v) for v in row])
        count += 1
    # A byte-order mark lets Excel open the UTF-8 file with names such as "Ọ̀ṣun" intact.
    return "﻿" + buffer.getvalue(), count


def request_register(requests):
    header = ["Reference", "Title", "Status", "Requester", "Current approver", "Current stage due", "Overdue",
              "Workflow version", "Revisions", "Review cycles", "Raised", "First submitted", "Final decision",
              "Withdrawal reason"]
    requests = requests.annotate(
        n_revisions=Count("revisions", distinct=True), n_cycles=Count("cycles", distinct=True),
        first_submitted=Min("cycles__started_at"),
    ).select_related("project", "requester", "workflow_version")
    final = dict(
        ReviewCycle.objects.filter(request__in=requests.values("pk"),
                                   outcome__in=[ReviewCycle.Outcome.APPROVED, ReviewCycle.Outcome.REJECTED])
        .values_list("request", "ended_at")
    )
    rows = (
        [r.reference, r.title, r.get_state_display(), r.requester.email, r.current_approver_name, r.current_due_at,
         "yes" if r.is_overdue else "no", r.workflow_version.number if r.workflow_version else "",
         r.n_revisions, r.n_cycles, r.created_at, r.first_submitted, final.get(r.pk), r.closed_reason]
        for r in requests
    )
    return to_csv(header, rows)


def decision_history(requests):
    """One row per decision, with the exact document versions the approver reviewed."""
    header = ["Reference", "Title", "Cycle", "Revision", "Stage", "Stage name", "Approver", "Outcome", "Reason",
              "Decided at", "Documents reviewed (name, version, SHA-256)"]
    decisions = (
        Decision.objects.filter(task__cycle__request__in=requests.values("pk"))
        .select_related("actor", "task__cycle__revision", "task__cycle__request__project")
        .prefetch_related(Prefetch(
            "task__cycle__revision__revision_documents",
            queryset=RevisionDocument.objects.select_related("document_version__document"),
        ))
        .order_by("task__cycle__request__project__code", "task__cycle__request__number", "task__cycle__number",
                  "task__position")
    )

    def evidence(revision):
        return "; ".join(
            f"{rd.document_version.document.name} v{rd.document_version.number} {rd.document_version.sha256}"
            for rd in revision.revision_documents.all()
        )

    rows = (
        [d.task.cycle.request.reference, d.task.cycle.request.title, d.task.cycle.number,
         d.task.cycle.revision.number, d.task.position, d.task.name, d.actor.email, d.get_outcome_display(),
         d.reason, d.created_at, evidence(d.task.cycle.revision)]
        for d in decisions
    )
    return to_csv(header, rows)


def audit_log(project):
    header = ["When", "Actor", "Action", "Request", "Summary", "Details (JSON)"]
    events = AuditEvent.objects.filter(project=project).select_related("actor", "request__project").order_by("created_at", "id")
    rows = (
        [e.created_at, e.actor.email if e.actor else "system", e.action, e.request.reference if e.request else "",
         e.summary, json.dumps(e.data, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True)]
        for e in events
    )
    return to_csv(header, rows)


EXPORTS = {
    "requests": ("Request register", request_register),
    "decisions": ("Decision history", decision_history),
    "audit": ("Audit log", None),
}
