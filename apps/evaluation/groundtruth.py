"""Ground truth, scenario sets A and B, and the generation specification.

The ground truth is for scoring only and must not be shown to participants.
"""
import csv
import hashlib
import json
from pathlib import Path

from .scenario import DOMAIN, OUTCOME_MIX, PATTERNS, STAGES, TASK_DESIGNS, TASK_PROJECTS, DocVersion

STATE_LABEL = {
    "APPROVED": "Approved", "REJECTED": "Rejected", "CHANGES_REQUESTED": "Changes requested",
    "CANCELLED": "Cancelled", "DRAFT": "Draft", "IN_REVIEW": "In review",
}
OUTCOME_LABEL = {"APPROVE": "Approved", "REJECT": "Rejected", "REQUEST_CHANGES": "Changes requested"}


def _person(scenario, key):
    p = scenario.person(key)
    return {"name": p.name, "email": p.email}


def request_truth(scenario, story, realisation):
    current = None
    if story.state == "IN_REVIEW":
        stage = story.cycles[-1].waiting_stage
        current = {"stage": stage, "stage_name": STAGES[stage - 1][0],
                   "approver": _person(scenario, scenario.roles[story.project][STAGES[stage - 1][1]])}
    elif story.state == "CHANGES_REQUESTED":
        current = {"stage": None, "stage_name": "Requester to revise", "approver": _person(scenario, story.requester)}
    return {
        "ref": story.ref,
        "project": story.project,
        "title": story.title,
        "requester": _person(scenario, story.requester),
        "state": story.state,
        "state_label": STATE_LABEL[story.state],
        "next_to_act": current,
        "raised_at": story.raised_at.isoformat(),
        "revisions": [
            {"revision": c.revision, "cycle": c.number, "submitted_at": c.submitted_at.isoformat(),
             "documents": [{"document": v.doc, "version": v.number, "filename": v.filename, "sha256": v.sha256}
                           for v in c.docs]}
            for c in story.cycles
        ],
        "decisions": [
            {"cycle": c.number, "revision": c.revision, "stage": d.stage, "stage_name": STAGES[d.stage - 1][0],
             "approver": _person(scenario, d.approver), "outcome": OUTCOME_LABEL[d.outcome], "reason": d.reason,
             "at": d.at.isoformat()}
            for c in story.cycles for d in c.decisions
        ],
        "withdrawal": (
            {"by": _person(scenario, story.withdrawn[0]), "reason": story.withdrawn[1],
             "at": story.withdrawn[2].isoformat()} if story.withdrawn else None
        ),
        "all_document_versions": [
            {"document": v.doc, "version": v.number, "filename": v.filename, "sha256": v.sha256,
             "uploaded_at": v.at.isoformat()} for v in story.versions
        ],
        "baseline_patterns": sorted(story.patterns),
        "baseline_realisation": realisation.get(story.ref, {}),
        "task": story.task or None,
    }


def write_ground_truth(scenario, realisation, out_dir):
    folder = Path(out_dir) / "ground_truth"
    folder.mkdir(parents=True, exist_ok=True)
    records = [request_truth(scenario, s, realisation) for s in scenario.stories]
    data = {
        "notice": "Scoring key for the Flowbridge evaluation. Do not show to participants. "
                  "ZTL is a fictional organisation; all data are synthetic.",
        "seed": scenario.seed,
        "anchor": scenario.anchor.isoformat(),
        "requests": records,
    }
    text = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)
    (folder / "ground_truth.json").write_text(text + "\n", encoding="utf-8")
    with open(folder / "requests.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Ref", "State", "Next to act", "Stage", "Review cycles", "Decisions", "Patterns", "Task"])
        for r in records:
            nxt = r["next_to_act"] or {}
            writer.writerow([r["ref"], r["state_label"], (nxt.get("approver") or {}).get("name", ""),
                             nxt.get("stage_name", ""), len(r["revisions"]), len(r["decisions"]),
                             " ".join(r["baseline_patterns"]), r["task"] or ""])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- scenario sets


T1_BRIEFS = {
    "A": ("Add a maximum loan amount check to the loan application form",
          "Reject applications above the product's maximum loan amount before credit scoring.",
          "Low", "loan-limit-check"),
    "B": ("Add a daily spend cap to the airtime top-up API",
          "Reject top-ups that would take a subscriber over the daily spend cap.",
          "Low", "daily-spend-cap"),
}


def _t1_document(set_name, persona_name):
    title, summary, risk, slug = T1_BRIEFS[set_name]
    text = (f"# Design note: {title}\n\nDocument version: 1\nPrepared by: {persona_name}\n\n"
            f"## Summary\n{summary}\n\n## Risk\n{risk}. Rollback: switch the check off with its feature flag.\n\n"
            "---\nSynthetic document for the fictional organisation Zenkora Technologies Limited (ZTL).\n")
    return f"{slug}-design-note.md", text.encode("utf-8")


def _t3_document(story):
    doc = story.cycles[-1].docs[0]
    content = doc.content.decode("utf-8").replace(
        f"Document version: {doc.number}", f"Document version: {doc.number + 1}"
    ).replace("## Changes in this version\n", "## Changes in this version\nAddresses the reviewer's request: ")
    return DocVersion(doc.doc, doc.title, doc.number + 1, doc.at, content.encode("utf-8"))


def write_scenario_sets(scenario, out_dir):
    root = Path(out_dir)
    keys = []
    for set_name, code in TASK_PROJECTS.items():
        t = scenario.tasks[set_name]
        persona = scenario.person(t["persona"])
        folder = root / "scenario-sets" / set_name
        materials = folder / "materials"
        materials.mkdir(parents=True, exist_ok=True)

        t1_name, t1_bytes = _t1_document(set_name, persona.name)
        (materials / t1_name).write_bytes(t1_bytes)
        t3_doc = _t3_document(t["T3"])
        (materials / f"T3-{t3_doc.filename}").write_bytes(t3_doc.content)

        t2, t3, t4, t5 = t["T2"], t["T3"], t["T4"], t["T5"]
        t3_changes = t3.cycles[-1].decisions[-1]
        t4_final = t4.cycles[-1].decisions[-1]
        title1, summary1, risk1, _ = T1_BRIEFS[set_name]
        cards = f"""# Scenario set {set_name}: task cards

You are **{persona.name}**, a software engineer on the {code} project at Zenkora Technologies Limited
(a fictional company). Sign in as `{persona.email}` when using Flowbridge.

Work at your normal pace. Say "done" when you finish each task. If you cannot finish, say "I'm stuck";
that is useful information, not a failure.

## T1 · Raise a change request

Raise a change request for: **{title1}**.
Purpose: {summary1} Risk: {risk1}; rollback by switching the feature flag off.
Attach the design note `materials/{t1_name}` and send it for review.

## T2 · Find where a request stands

What is the current status of **{t2.ref}** ("{t2.title}"), and who needs to act next?

## T3 · Respond to a request for changes

{scenario.person(t3_changes.approver).name} asked for changes to your request **{t3.ref}** ("{t3.title}").
Revise it using the updated document `materials/T3-{t3_doc.filename}` and send it back for review.

## T4 · Find the exact document version

{scenario.person(t4_final.approver).name} gave the final approval on **{t4.ref}** ("{t4.title}").
Which version of each document did they approve? Name each document and its version.

## T5 · Reconstruct the decisions

List, in order, every decision made on **{t5.ref}** ("{t5.title}"): who decided, at which stage, what they
decided and, where there was one, the reason.
"""
        (folder / "tasks.md").write_text(cards, encoding="utf-8")

        def fmt_decisions(story):
            lines = []
            for c in story.cycles:
                for d in c.decisions:
                    reason = f' — "{d.reason}"' if d.reason else ""
                    lines.append(f"   {len(lines) + 1}. Cycle {c.number}, stage {d.stage} ({STAGES[d.stage - 1][0]}): "
                                 f"{scenario.person(d.approver).name}: {OUTCOME_LABEL[d.outcome]}{reason}")
            return "\n".join(lines)

        t2_stage = t2.cycles[-1].waiting_stage
        t2_next = scenario.person(scenario.roles[code][STAGES[t2_stage - 1][1]]).name
        t4_docs = "\n".join(f"   - {v.title}: version {v.number} (`{v.filename}`, SHA-256 {v.sha256[:16]}…)"
                            for v in t4.cycles[-1].docs)
        key = f"""# Answer key, scenario set {set_name} (scoring only; do not show participants)

Persona: {persona.name} ({persona.email}), requester on {code}.

**T1.** Success if the request reaches the project manager ({scenario.person(scenario.roles[code]['pm']).name})
for review with: the title, the purpose, the risk, the rollback, and the design note `{t1_name}` attached.
Flowbridge: the request is submitted and stage 1 is active. Baseline: an email to the PM (copying
{code.lower()}-changes@{DOMAIN}) with the attachment, plus a row in the change log.

**T2.** {t2.ref}: **In review, awaiting {STAGES[t2_stage - 1][0].lower()}**. Next to act: **{t2_next}**.
Score status and person separately (retrieval accuracy: 2 answers). Baseline traps: P1 and P2
(the log shows an out-of-date status and owner).

**T3.** {t3.ref}: success if version {t3_doc.number} of the {t3_doc.title.lower()} (`T3-{t3_doc.filename}`,
SHA-256 {t3_doc.sha256[:16]}…) is attached and the request is sent back for review. Flowbridge: resubmitted as
revision {len(t3.cycles) + 1}, cycle {len(t3.cycles) + 1} at stage 1. Baseline: a reply to the
thread with the attachment, addressed to the PM or to {scenario.person(t3_changes.approver).name}.

**T4.** {t4.ref}, final approval by {scenario.person(t4_final.approver).name} (cycle {t4.cycles[-1].number},
stage {t4_final.stage}). Approved versions:
{t4_docs}
Score each document separately (retrieval accuracy). Baseline trap: P3 (misleading copies on the drive).

**T5.** {t5.ref}, {sum(len(c.decisions) for c in t5.cycles)} decisions:
{fmt_decisions(t5)}
Score: decisions listed correctly and in order, out of {sum(len(c.decisions) for c in t5.cycles)}
(reconstruction accuracy); and separately, whether the reason for the request for changes was recovered.
Baseline trap: P4 (that reason is missing from email and the log).
"""
        keys.append((set_name, key))
        gt = root / "ground_truth"
        gt.mkdir(parents=True, exist_ok=True)
        (gt / f"answer-key-{set_name}.md").write_text(key, encoding="utf-8")
    return keys


# --------------------------------------------------------------------------- specification


def write_accounts(scenario, out_dir):
    """Every synthetic account with its project roles (not a scoring key; safe to share with moderators)."""
    rows = []
    for code, r in scenario.roles.items():
        rows += [(r["pm"], code, "PM"), (r["tl"], code, "APPROVER"), (r["po"], code, "APPROVER")]
        rows += [(k, code, "REQUESTER") for k in r["requesters"]] + [(k, code, "VIEWER") for k in r["viewers"]]
    with open(Path(out_dir) / "accounts.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["email", "name", "job_title", "staff_code", "project", "role"])
        for key, code, role in sorted(rows, key=lambda x: (x[1], x[2], x[0])):
            p = scenario.person(key)
            writer.writerow([p.email, p.name, p.title, p.code, code, role])


def write_spec(scenario, out_dir, fingerprint, realisation):
    by_kind = {}
    for s in scenario.stories:
        by_kind[s.kind] = by_kind.get(s.kind, 0) + 1
    mix = "\n".join(f"| {k} | {share:.1%} | {by_kind.get(k, 0)} |" for k, share in OUTCOME_MIX)
    pats = "\n".join(
        f"| {code} | {name} | {desc} | {rate:.0%} | {scenario.eligible_counts[code]} | {scenario.pattern_counts[code]} |"
        for code, (name, desc, rate) in PATTERNS.items()
    )
    designs = "\n".join(f"| {name} | {kind} | {', '.join(f'{k}={v}' for k, v in d.items())} |"
                        for name, kind, d in TASK_DESIGNS)
    tasks = "\n".join(
        f"| {set_name} | {t['project']} | {scenario.person(t['persona']).name} | "
        + " | ".join(f"{t[n].ref} ({', '.join(sorted(t[n].patterns)) or 'none'})" for n in ("T2", "T3", "T4", "T5"))
        + " |"
        for set_name, t in scenario.tasks.items()
    )
    spec = f"""# Evaluation dataset: generation specification

Zenkora Technologies Limited (ZTL) is a fictional organisation. Every person, project, request, message and
document in this dataset is synthetic.

## Reproducing it

```bash
python manage.py generate_evaluation_data --seed {scenario.seed} --load --flush
```

The same seed always produces the same scenario, files and ground truth.
Ground-truth fingerprint (SHA-256 of `ground_truth/ground_truth.json`): `{fingerprint}`

| Parameter | Value |
|---|---|
| Seed | {scenario.seed} |
| Scenario "today" | {scenario.anchor:%d %B %Y, %H:%M} (Africa/Lagos) |
| Projects | 6 (PAY, CRM, HRM, LND, TEL, GOV), {len(scenario.stories) // 6} requests each |
| Staff | {len(scenario.people)} coded synthetic users (6 PMs, 6 technical leads, 6 product owners, 18 requesters, 4 QA viewers) plus one administrator |
| Requests | {len(scenario.stories)} software change requests raised over about five months |
| Approval chain | Project manager review → technical lead review → product owner sign-off (sequential) |
| Names | Faker locales yo_NG, ig_NG, ha_NG, en_NG, seeded |
| Text | Request, document, comment and email text from fixed English templates, chosen with the same seed |

## Outcome mix

| Outcome | Target share | Requests |
|---|---|---|
{mix}

## Problem patterns injected into the baseline

Patterns are injected into the baseline artefacts only. The system dataset holds the same facts without them.
Each pattern applies to an exact number of eligible requests: round(rate × eligible).

| Code | Pattern | Description | Rate | Eligible | Injected |
|---|---|---|---|---|---|
{pats}

Eligibility: P1, any submitted request; P2, any request with at least one decision; P3, any submitted request
with more than one version of a document; P4, any submitted request with at least one decision reason.

How each pattern appears:

- **P1**: approval emails say "Passing it along" instead of naming the next approver, and the log's *With*
  column is blank, "TBC" or wrong. For requests in review, the chat also names the wrong person.
- **P2**: the log keeps the status from soon after first submission. For half of these, the chat claims the
  request is approved when it is not.
- **P3**: emails say the documents are on the drive instead of attaching them, and the drive folder also holds
  misleading copies (`*_FINAL.md` holds version 1, `* (1).md` duplicates the latest,
  `*_final_reviewed.md` holds the previous version).
- **P4**: rejection and change emails say the comments were given "on the call". For about half, the reason
  survives only in the chat; otherwise it is recorded nowhere. Approval notes are also left out.

## Matched task requests (scenario sets A and B)

Both sets use the same task designs:

| Task | Request kind | Fixed design |
|---|---|---|
{designs}

| Set | Project | Persona | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|---|
{tasks}

## Files

- `baseline/`: the manual-process sandbox (email, chat, spreadsheet, shared drive)
- `scenario-sets/A`, `scenario-sets/B`: task cards and the files participants need
- `ground_truth/`: scoring keys (not for participants)
- The system dataset is loaded into Flowbridge with `--load`; every record goes through `WorkflowService`
  on a simulated clock, so it has the same evidence and audit trail as real use.
"""
    (Path(out_dir) / "GENERATION-SPEC.md").write_text(spec, encoding="utf-8")
