"""The ZTL evaluation scenario (Section 3.1.3), built from a fixed random seed.

One abstract scenario is built first. It is then rendered three ways, so that
both evaluation conditions hold exactly the same underlying facts:

* the system dataset, loaded into Flowbridge through WorkflowService (system.py);
* the baseline artefacts: email, chat export, spreadsheet log, shared drive (baseline.py);
* the ground truth used for scoring (groundtruth.py).

Zenkora Technologies Limited (ZTL) is fictional. Every person, project,
request and document here is synthetic.
"""
import hashlib
import random
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from faker import Faker

LAGOS = ZoneInfo("Africa/Lagos")
DEFAULT_SEED = 2026
DEFAULT_REQUESTS = 120
DEFAULT_ANCHOR = datetime(2026, 11, 2, 9, 0, tzinfo=LAGOS)  # "today" in the scenario
DOMAIN = "ztl.example"

PROJECTS = [
    ("PAY", "Payments Gateway Upgrade", "Card and transfer gateway for a retail bank client"),
    ("CRM", "Client Portal Revamp", "Self-service portal for an insurance client"),
    ("HRM", "HR Mobile App", "Internal staff self-service app"),
    ("LND", "Loan Origination Platform", "Digital loan applications for a microfinance client"),
    ("TEL", "Telecom Billing Integration", "Billing and top-up integration for a telecoms client"),
    ("GOV", "State Revenue e-Filing", "Online tax filing for a state revenue agency client"),
]
STAGES = [("Project manager review", "pm", 24), ("Technical lead review", "tl", 48), ("Product owner sign-off", "po", 48)]
STAGE_MEDIAN_HOURS = {1: 6, 2: 20, 3: 14}

# Outcome mix for the request history (Table 3.x: approved, rejected, changes requested, cancelled, pending).
OUTCOME_MIX = [
    ("APPROVED_1", 0.35),   # approved in the first review cycle
    ("APPROVED_2", 0.15),   # approved after one request for changes
    ("REJECTED", 0.125),
    ("CHANGES", 0.10),      # changes requested, waiting for the requester
    ("CANCELLED", 0.075),
    ("IN_REVIEW", 0.15),    # pending with an approver
    ("DRAFT", 0.05),
]
FINAL_STATE = {
    "APPROVED_1": "APPROVED", "APPROVED_2": "APPROVED", "REJECTED": "REJECTED", "CHANGES": "CHANGES_REQUESTED",
    "CANCELLED": "CANCELLED", "IN_REVIEW": "IN_REVIEW", "DRAFT": "DRAFT",
}

# The four problem patterns of Section 2.1.3, injected into the baseline only, at documented rates.
PATTERNS = {
    "P1": ("Unclear ownership", "No single record shows who must act next", 0.30),
    "P2": ("Status divergence", "Status differs between email, chat and spreadsheet", 0.25),
    "P3": ("Version confusion", "Several copies of a document circulate under misleading names", 0.50),
    "P4": ("Lost rationale", "A decision's reason is missing from email and the spreadsheet", 0.30),
}

TASK_PROJECTS = {"A": "LND", "B": "TEL"}  # scenario set A uses LND, set B uses TEL (matched designs)
# Each set's task requests follow the same design, so sets A and B are equally hard.
TASK_DESIGNS = [
    ("T2", "IN_REVIEW", {"approvals_before_wait": 1, "two_cycles": False, "n_docs": 1, "extra_draft": False}),
    ("T3", "CHANGES", {"fail_stage": 2, "two_cycles": False, "n_docs": 1, "extra_draft": False, "persona": True}),
    ("T4", "APPROVED_2", {"fail_stage": 2, "n_docs": 2, "extra_draft": False}),
    ("T5", "APPROVED_2", {"fail_stage": 3, "n_docs": 1, "extra_draft": False}),
]

COMPONENTS = {
    "PAY": ["transfer callback handler", "card tokenisation service", "settlement report", "merchant API",
            "refund workflow", "fraud rules engine", "payment status page"],
    "CRM": ["policy search page", "claims upload form", "customer login", "premium calculator", "agent dashboard",
            "renewal reminder job", "document vault"],
    "HRM": ["leave request screen", "payslip viewer", "staff directory sync", "push notification service",
            "expense claim form", "onboarding checklist", "attendance module"],
    "LND": ["credit scoring service", "loan application form", "KYC verification step", "repayment schedule",
            "disbursement API", "loan officer dashboard", "BVN lookup integration"],
    "TEL": ["airtime top-up API", "billing reconciliation job", "USSD menu", "bundle catalogue",
            "invoice generator", "subscriber lookup", "usage alert service"],
    "GOV": ["tax return form", "TIN validation", "payment receipt service", "filing deadline reminders",
            "assessment calculator", "taxpayer portal login", "audit trail report"],
}
ACTIONS = [
    ("Add input validation to the {c}", "Reject malformed input at the {c} before it reaches downstream systems."),
    ("Upgrade the logging library in the {c}", "Move the {c} to the current logging library release."),
    ("Add rate limiting to the {c}", "Limit requests per client on the {c} to protect shared capacity."),
    ("Improve error messages in the {c}", "Replace generic errors in the {c} with actionable messages."),
    ("Add retry with back-off to the {c}", "Retry transient failures in the {c} with exponential back-off."),
    ("Cache lookups in the {c}", "Cache read-heavy lookups in the {c} for five minutes."),
    ("Add an audit field to the {c}", "Record who last changed each record in the {c}."),
    ("Move the {c} to the new database cluster", "Migrate the {c} to the new managed database cluster."),
    ("Add CSV export to the {c}", "Let authorised staff export the {c} data as CSV."),
    ("Harden session handling in the {c}", "Shorten idle sessions and rotate tokens in the {c}."),
    ("Remove the deprecated endpoint from the {c}", "Retire the old endpoint in the {c} after the migration."),
    ("Add monitoring alerts for the {c}", "Alert the on-call engineer when the {c} error rate rises."),
]
RISKS = ["Low", "Low", "Medium", "Medium", "High"]
DOC_TYPES = [("design-note", "Design note"), ("test-plan", "Test plan"), ("rollback-plan", "Rollback plan"),
             ("data-mapping", "Data mapping")]
CHANGE_REASONS = [
    "Add the rollback steps and who will run them.",
    "Attach test evidence for the failure cases.",
    "State the expected downtime and the change window.",
    "Confirm the data retention period with the client.",
    "Describe how existing records will be migrated.",
    "Add the monitoring you will watch after release.",
    "Clarify which client environments are affected.",
]
REJECT_REASONS = [
    "Conflicts with the client's security policy.",
    "Duplicates work already planned for the next release.",
    "The benefit does not justify the risk this quarter.",
    "Out of scope for the current contract; raise it as a change order.",
]
APPROVE_NOTES = ["", "", "", "Looks good.", "Fine from my side.", "Approved; please schedule outside peak hours.",
                 "Approved. Keep the feature flag off until sign-off."]
WITHDRAW_REASONS = [
    "Superseded by a combined change request.",
    "The client has paused this work.",
    "Raised in error.",
    "No longer needed after the vendor fix.",
]
CLIENT_IMPACT = [
    "None visible to end users.",
    "Brief slowdown possible during the release window.",
    "Customers see clearer error messages.",
    "Support staff need a short briefing before release.",
    "The client's operations team must be told the release date.",
    "No downtime expected; the change is behind a feature flag.",
]
SUMMARY_SENTENCES = [
    "This document describes the change, the components it touches and how it will be tested.",
    "The change is limited to the {c} and does not alter any shared database tables.",
    "Configuration is held in the environment, so the change can be switched off without a redeploy.",
    "Existing records are not modified; new fields default to empty for older records.",
    "Monitoring dashboards will be checked for one hour after release.",
    "The client's acceptance criteria are listed in the test plan.",
    "Load on the {c} is expected to stay within current limits.",
    "The rollback has been rehearsed in the staging environment.",
]
REVISION_NOTES = [
    "added the rollback steps and named who will run them",
    "attached test evidence for the failure cases",
    "stated the change window and expected downtime",
    "confirmed the data retention period with the client",
    "described how existing records will be migrated",
    "listed the monitoring to watch after release",
    "clarified which client environments are affected",
]

COMMENT_PAIRS = [
    ("Has this been tested against the staging data set?", "Yes, the staging run passed last night."),
    ("Which release window are you targeting?", "The Thursday evening window."),
    ("Does this need a client notice?", "No, there is no visible change for end users."),
    ("Is the rollback automated?", "Partly; the database step is manual and documented."),
]


@dataclass
class Person:
    key: str
    name: str
    email: str
    title: str
    code: str


@dataclass
class DocVersion:
    doc: str          # e.g. "design-note"
    title: str        # e.g. "Design note"
    number: int
    at: datetime
    content: bytes = b""

    @property
    def filename(self):
        return f"{self.doc}.md" if self.number == 1 else f"{self.doc}_v{self.number}.md"

    @property
    def sha256(self):
        return hashlib.sha256(self.content).hexdigest()


@dataclass
class Decision:
    stage: int
    approver: str
    outcome: str      # APPROVE, REJECT, REQUEST_CHANGES
    reason: str
    at: datetime


@dataclass
class Cycle:
    number: int
    revision: int
    submitted_at: datetime
    docs: list            # DocVersion objects frozen into this revision
    decisions: list = field(default_factory=list)
    outcome: str = ""     # APPROVED, REJECTED, CHANGES_REQUESTED, CANCELLED, "" if open
    waiting_stage: int = 0


@dataclass
class Story:
    project: str
    kind: str
    requester: str
    raised_at: datetime
    action: tuple
    component: str
    risk: str
    number: int = 0
    title: str = ""
    description: str = ""
    versions: list = field(default_factory=list)      # every DocVersion in upload order
    cycles: list = field(default_factory=list)
    comments: list = field(default_factory=list)      # (author_key, text, at)
    withdrawn: tuple | None = None                    # (actor_key, reason, at, state_before)
    revised_description: str = ""                     # working copy edit before resubmission, if any
    patterns: set = field(default_factory=set)
    task: str = ""                                    # e.g. "A-T2"
    design: dict = field(default_factory=dict)        # fixed choices for task requests

    @property
    def ref(self):
        return f"{self.project}-{self.number:03d}"

    @property
    def state(self):
        return FINAL_STATE[self.kind]

    def events_end(self):
        times = [self.raised_at] + [v.at for v in self.versions] + [c.submitted_at for c in self.cycles]
        times += [d.at for c in self.cycles for d in c.decisions] + [t for _, _, t in self.comments]
        if self.withdrawn:
            times.append(self.withdrawn[2])
        return max(times)


@dataclass
class Scenario:
    seed: int
    anchor: datetime
    people: dict           # key -> Person
    roles: dict            # project code -> {"pm": key, "tl": key, "po": key, "requesters": [...], "viewers": [...]}
    stories: list
    pattern_counts: dict
    eligible_counts: dict

    def story(self, ref):
        return next(s for s in self.stories if s.ref == ref)

    def person(self, key):
        return self.people[key]


def _ascii(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _allocate(total, mix):
    """Largest-remainder allocation of ``total`` items across the mix."""
    raw = [(name, total * share) for name, share in mix]
    counts = {name: int(value) for name, value in raw}
    remainder = total - sum(counts.values())
    for name, value in sorted(raw, key=lambda x: x[1] - int(x[1]), reverse=True)[:remainder]:
        counts[name] += 1
    return counts


def _hours(rng, median):
    return max(0.5, min(120.0, rng.lognormvariate(0, 0.8) * median))


# --------------------------------------------------------------------------- people


def build_people(rng, faker_seed):
    fakers = []
    for i, locale in enumerate(["yo_NG", "ig_NG", "ha_NG", "en_NG"]):
        f = Faker(locale)
        f.seed_instance(faker_seed + i)
        fakers.append(f)
    used_names, used_emails = set(), set()
    people, counter = {}, [0]

    def new(title):
        while True:
            f = fakers[counter[0] % len(fakers)]
            first, last = f.first_name(), f.last_name()
            name = f"{first} {last}"
            local = re.sub(r"[^a-z]", "", _ascii(first)) + "." + re.sub(r"[^a-z]", "", _ascii(last))
            if name not in used_names and local not in used_emails and len(local) > 3:
                break
        counter[0] += 1
        used_names.add(name)
        used_emails.add(local)
        code = f"ZTL-{counter[0]:03d}"
        person = Person(key=local, name=name, email=f"{local}@{DOMAIN}", title=title, code=code)
        people[local] = person
        return local

    roles = {}
    for code, _, _ in PROJECTS:
        roles[code] = {
            "pm": new("Project manager"),
            "tl": new("Technical lead"),
            "po": new("Product owner"),
            "requesters": [new("Software engineer") for _ in range(3)],
            "viewers": [],
        }
    viewers = [new("Quality assurance analyst") for _ in range(4)]
    codes = [c for c, _, _ in PROJECTS]
    for i, viewer in enumerate(viewers):
        for code in (codes[i], codes[(i + 2) % 6], codes[(i + 4) % 6]):
            roles[code]["viewers"].append(viewer)
    return people, roles


# --------------------------------------------------------------------------- stories


def _plan_outcomes(rng, total):
    """Return {project: [(kind, design, task_name), ...]} with an even spread and the task requests reserved."""
    counts = _allocate(total, OUTCOME_MIX)
    pool = [kind for kind, n in counts.items() for _ in range(n)]
    per_project = {code: [] for code, _, _ in PROJECTS}
    for code in TASK_PROJECTS.values():
        for name, kind, design in TASK_DESIGNS:
            pool.remove(kind)
            per_project[code].append((kind, design, name))
    rng.shuffle(pool)
    codes = [c for c, _, _ in PROJECTS]
    quotas = _allocate(total, [(c, 1 / len(codes)) for c in codes])
    for code in codes:
        while len(per_project[code]) < quotas[code]:
            per_project[code].append((pool.pop(), {}, ""))
    assert not pool
    return per_project


def _simulate(rng, story, roles, faker):
    """Fill in versions, cycles, decisions, comments and withdrawal for one story."""
    r = roles[story.project]
    approvers = {1: r["pm"], 2: r["tl"], 3: r["po"]}
    t = story.raised_at
    design = story.design
    n_docs = design.get("n_docs") or rng.choice([1, 1, 2])
    doc_types = rng.sample(DOC_TYPES, n_docs)
    for doc, title in doc_types:
        story.versions.append(DocVersion(doc, title, 1, t))
    if design.get("extra_draft", rng.random() < 0.3):  # an extra draft version before submission
        doc, title = doc_types[0]
        t += timedelta(hours=rng.uniform(2, 30))
        story.versions.append(DocVersion(doc, title, 2, t))

    if story.kind == "DRAFT":
        return
    if story.kind == "CANCELLED" and rng.random() < 0.3:
        t += timedelta(hours=rng.uniform(4, 72))
        story.withdrawn = (story.requester, rng.choice(WITHDRAW_REASONS), t, "DRAFT")
        return

    def latest_versions():
        latest = {}
        for v in story.versions:
            latest[v.doc] = v
        return [latest[d] for d, _ in doc_types]

    plan = []  # per cycle: list of outcomes in stage order; last may be "WAIT" or "WITHDRAW"
    kind = story.kind
    two_cycles = kind == "APPROVED_2" or design.get(
        "two_cycles", kind in ("REJECTED", "CHANGES", "IN_REVIEW") and rng.random() < 0.25)

    def failing(final):
        stage = design.get("fail_stage") or rng.randint(1, 3)
        return ["APPROVE"] * (stage - 1) + [final]

    if two_cycles:
        plan.append(failing("REQUEST_CHANGES"))
    if kind in ("APPROVED_1", "APPROVED_2"):
        plan.append(["APPROVE"] * 3)
    elif kind == "REJECTED":
        plan.append(failing("REJECT"))
    elif kind == "CHANGES":
        plan.append(failing("REQUEST_CHANGES"))
    elif kind == "IN_REVIEW":
        waits_after = design.get("approvals_before_wait", rng.randint(0, 2))
        plan.append(["APPROVE"] * waits_after + ["WAIT"])
    elif kind == "CANCELLED":
        plan.append(["APPROVE"] * rng.randint(0, 2) + ["WITHDRAW"])

    revision = 0
    for index, outcomes in enumerate(plan, start=1):
        if index > 1:  # revise after a request for changes
            t += timedelta(hours=rng.uniform(6, 72))
            doc, title = doc_types[0]
            number = max(v.number for v in story.versions if v.doc == doc) + 1
            story.versions.append(DocVersion(doc, title, number, t))
            t += timedelta(minutes=rng.uniform(5, 90))
        else:
            t += timedelta(hours=rng.uniform(1, 30))
        revision += 1
        cycle = Cycle(number=index, revision=revision, submitted_at=t, docs=latest_versions())
        story.cycles.append(cycle)
        for stage, outcome in enumerate(outcomes, start=1):
            if outcome == "WAIT":
                cycle.waiting_stage = stage
                break
            if outcome == "WITHDRAW":
                t += timedelta(hours=_hours(rng, STAGE_MEDIAN_HOURS[stage]) * 0.6)
                actor = rng.choice([story.requester, r["pm"]])
                story.withdrawn = (actor, rng.choice(WITHDRAW_REASONS), t, "IN_REVIEW")
                cycle.outcome = "CANCELLED"
                break
            t += timedelta(hours=_hours(rng, STAGE_MEDIAN_HOURS[stage]))
            if outcome == "APPROVE":
                reason = rng.choice(APPROVE_NOTES)
            elif outcome == "REJECT":
                reason = rng.choice(REJECT_REASONS)
            else:
                reason = rng.choice(CHANGE_REASONS)
            cycle.decisions.append(Decision(stage, approvers[stage], outcome, reason, t))
            if outcome == "REJECT":
                cycle.outcome = "REJECTED"
            elif outcome == "REQUEST_CHANGES":
                cycle.outcome = "CHANGES_REQUESTED"
        else:
            if not cycle.outcome:
                cycle.outcome = "APPROVED"
        if rng.random() < 0.35:  # a short exchange during review
            question, answer = rng.choice(COMMENT_PAIRS)
            asker = approvers[rng.randint(1, max(1, len(cycle.decisions) or 1))]
            q_at = cycle.submitted_at + timedelta(minutes=rng.uniform(20, 120))
            a_at = q_at + timedelta(minutes=rng.uniform(10, 90))
            story.comments += [(asker, question, q_at), (story.requester, answer, a_at)]

    if kind == "CANCELLED" and story.withdrawn is None:  # withdrawn after changes were requested
        t += timedelta(hours=rng.uniform(12, 96))
        story.withdrawn = (story.requester, rng.choice(WITHDRAW_REASONS), t, "CHANGES_REQUESTED")


def _shift(story, delta):
    story.raised_at += delta
    for v in story.versions:
        v.at += delta
    for c in story.cycles:
        c.submitted_at += delta
        for d in c.decisions:
            d.at += delta
    story.comments = [(a, txt, t + delta) for a, txt, t in story.comments]
    if story.withdrawn:
        a, reason, t, before = story.withdrawn
        story.withdrawn = (a, reason, t + delta, before)


def _render_texts(rng, story, scenario, faker):
    action_title, action_body = story.action
    story.title = action_title.format(c=story.component)
    requester = scenario.person(story.requester).name
    story.description = (
        f"{action_body.format(c=story.component)}\n"
        f"Risk: {story.risk}. Rollback: redeploy the previous release and restore the configuration snapshot.\n"
        f"Client impact: {rng.choice(CLIENT_IMPACT)}"
    )
    for v in story.versions:
        changes = "First issue." if v.number == 1 else f"Revised after review: {rng.choice(REVISION_NOTES)}."
        summary = " ".join(s.format(c=story.component) for s in rng.sample(SUMMARY_SENTENCES, 3))
        text = (
            f"# {v.title}: {story.title}\n\n"
            f"Request: {story.ref}\n"
            f"Document version: {v.number}\n"
            f"Prepared by: {requester}\n"
            f"Date: {v.at:%d %B %Y}\n\n"
            f"## Summary\n{summary}\n\n"
            f"## Changes in this version\n{changes}\n\n"
            f"---\nSynthetic document for the fictional organisation Zenkora Technologies Limited (ZTL).\n"
        )
        v.content = text.encode("utf-8")
    if story.kind != "DRAFT" and len(story.cycles) > 1 and rng.random() < 0.5:
        story.revised_description = story.description + "\nUpdated after review."


def _assign_patterns(rng, stories):
    submitted = [s for s in stories if s.cycles]
    decided = [s for s in submitted if any(c.decisions for c in s.cycles)]
    versioned = [s for s in stories if len(s.versions) > len({v.doc for v in s.versions}) and s.cycles]
    reasoned = [s for s in submitted if any(d.reason for c in s.cycles for d in c.decisions)]
    eligible = {"P1": submitted, "P2": decided, "P3": versioned, "P4": reasoned}
    counts = {}
    for code, (_, _, rate) in PATTERNS.items():
        pool = eligible[code]
        target = round(rate * len(pool))
        already = [s for s in pool if code in s.patterns]
        # Task requests carry only the patterns their task is designed to probe, so sets A and B match.
        rest = [s for s in pool if code not in s.patterns and not s.task]
        rng.shuffle(rest)
        for s in rest[: max(0, target - len(already))]:
            s.patterns.add(code)
        counts[code] = sum(1 for s in pool if code in s.patterns)
    return counts, {code: len(pool) for code, pool in eligible.items()}


def _choose_tasks(stories, roles):
    """Collect each set's task requests and force the baseline patterns each task is designed to probe."""
    chosen = {}
    forced = {"T2": {"P1", "P2"}, "T4": {"P3"}, "T5": {"P4"}}
    for set_name, code in TASK_PROJECTS.items():
        entry = {"persona": roles[code]["requesters"][0], "project": code}
        for story in stories:
            if story.task.startswith(f"{set_name}-"):
                name = story.task.split("-")[1]
                story.patterns |= forced.get(name, set())
                entry[name] = story
        chosen[set_name] = entry
    return chosen


def build_scenario(seed=DEFAULT_SEED, total=DEFAULT_REQUESTS, anchor=DEFAULT_ANCHOR):
    rng = random.Random(seed)
    faker = Faker("en_GB")
    faker.seed_instance(seed)
    people, roles = build_people(rng, seed)
    per_project = _plan_outcomes(rng, total)

    stories = []
    for code, plans in per_project.items():
        r = roles[code]
        for kind, design, task_name in plans:
            # The T3 request belongs to the set's persona, who signs in for the session.
            requester = r["requesters"][0] if design.get("persona") else rng.choice(r["requesters"][1:])
            story = Story(
                project=code, kind=kind, requester=requester,
                raised_at=anchor - timedelta(days=rng.uniform(10, 150), hours=rng.uniform(0, 10)),
                action=rng.choice(ACTIONS), component=rng.choice(COMPONENTS[code]), risk=rng.choice(RISKS),
                design=design,
            )
            if task_name:
                set_name = next(k for k, v in TASK_PROJECTS.items() if v == code)
                story.task = f"{set_name}-{task_name}"
            _simulate(rng, story, roles, faker)
            # Open work happened recently; closed work ended before "today".
            if kind in ("IN_REVIEW", "CHANGES", "DRAFT"):
                target_end = anchor - timedelta(hours=rng.uniform(2, 96))
                _shift(story, target_end - story.events_end())
            elif story.events_end() > anchor - timedelta(days=1):
                _shift(story, anchor - timedelta(days=rng.uniform(1, 5)) - story.events_end())
            stories.append(story)

    for code, _, _ in PROJECTS:
        mine = sorted((s for s in stories if s.project == code), key=lambda s: s.raised_at)
        for number, story in enumerate(mine, start=1):
            story.number = number

    scenario = Scenario(seed=seed, anchor=anchor, people=people, roles=roles, stories=[], pattern_counts={},
                        eligible_counts={})
    stories.sort(key=lambda s: (s.project, s.number))
    scenario.stories = stories
    for story in stories:
        _render_texts(rng, story, scenario, faker)
    scenario.tasks = _choose_tasks(stories, roles)
    scenario.pattern_counts, scenario.eligible_counts = _assign_patterns(rng, stories)
    return scenario
