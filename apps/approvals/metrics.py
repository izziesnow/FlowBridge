"""Figures for the project dashboard (FR12).

Every figure is computed from the requests passed in, so the dashboard
respects the same filters as the request list and the exports.
"""
from collections import defaultdict
from statistics import median

from django.db.models import Count, Min, Q
from django.utils import timezone

from .models import ApprovalRequest, Decision, RequestState, ReviewCycle, StageTask

FINAL_OUTCOMES = (ReviewCycle.Outcome.APPROVED, ReviewCycle.Outcome.REJECTED)


def _hours(delta):
    return round(delta.total_seconds() / 3600, 1)


def project_metrics(requests):
    ids = list(requests.values_list("pk", flat=True))
    requests = ApprovalRequest.objects.filter(pk__in=ids)  # drop list annotations before grouping
    now = timezone.now()

    by_state = dict(requests.order_by().values_list("state").annotate(n=Count("pk")))
    states = [(value, label, by_state.get(value, 0)) for value, label in RequestState.choices]
    total = sum(by_state.values())

    active = StageTask.objects.filter(cycle__request__in=ids, status=StageTask.Status.ACTIVE)
    overdue = active.filter(due_at__lt=now).count()

    # Time from first submission to the final decision, for requests that reached one.
    final_cycles = ReviewCycle.objects.filter(request__in=ids, outcome__in=FINAL_OUTCOMES).select_related("request")
    first_submit = dict(
        ReviewCycle.objects.filter(request__in=ids).values("request").annotate(t=Min("started_at")).values_list("request", "t")
    )
    durations = [_hours(c.ended_at - first_submit[c.request_id]) for c in final_cycles if c.ended_at]
    approved_cycles = [c for c in final_cycles if c.outcome == ReviewCycle.Outcome.APPROVED]
    first_pass = sum(1 for c in approved_cycles if c.number == 1)

    closed = requests.filter(state__in=[RequestState.APPROVED, RequestState.REJECTED]).order_by()
    closed_count = closed.count()
    closed_cycles = ReviewCycle.objects.filter(request__in=closed.values("pk")).count()

    waiting = (
        active.values("approver__full_name")
        .annotate(n=Count("pk"), late=Count("pk", filter=Q(due_at__lt=now)), oldest=Min("activated_at"))
        .order_by("-late", "-n", "approver__full_name")
    )
    waiting_rows = [
        {"approver": row["approver__full_name"], "active": row["n"], "overdue": row["late"],
         "oldest_hours": _hours(now - row["oldest"]) if row["oldest"] else None}
        for row in waiting
    ]

    per_stage = defaultdict(list)
    decided = StageTask.objects.filter(
        cycle__request__in=ids, status=StageTask.Status.COMPLETED, activated_at__isnull=False, completed_at__isnull=False
    ).values_list("position", "name", "activated_at", "completed_at")
    names = {}
    for position, name, start, end in decided:
        per_stage[position].append(_hours(end - start))
        names.setdefault(position, name)
    stage_rows = [
        {"position": p, "name": names[p], "decisions": len(v), "median_hours": round(median(v), 1)}
        for p, v in sorted(per_stage.items())
    ]

    outcomes = dict(
        Decision.objects.filter(task__cycle__request__in=ids).values_list("outcome").annotate(n=Count("pk"))
    )

    return {
        "total": total,
        "states": states,
        "max_state": max([n for _, _, n in states] or [0]) or 1,
        "open": sum(by_state.get(s, 0) for s in (RequestState.DRAFT, RequestState.IN_REVIEW, RequestState.CHANGES_REQUESTED)),
        "in_review": by_state.get(RequestState.IN_REVIEW, 0),
        "overdue": overdue,
        "median_hours_to_decision": round(median(durations), 1) if durations else None,
        "decided_requests": len(durations),
        "first_pass_rate": round(100 * first_pass / len(approved_cycles)) if approved_cycles else None,
        "approved": len(approved_cycles),
        "cycles_per_closed": round(closed_cycles / closed_count, 2) if closed_count else None,
        "waiting": waiting_rows,
        "stages": stage_rows,
        "decision_outcomes": [(label, outcomes.get(value, 0)) for value, label in Decision.Outcome.choices],
    }
