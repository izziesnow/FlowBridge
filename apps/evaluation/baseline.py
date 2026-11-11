"""Render the scenario as ZTL's manual baseline process (the comparison condition, Section 3.1.4).

The same facts become what a team using email, a chat group, a shared
spreadsheet and a shared drive would leave behind:

    baseline/mail/ztl-change-requests.mbox   every email (import into any mail client)
    baseline/mail/inbox.html                 the same emails in a searchable offline viewer
    baseline/mail/attachments/               files attached to those emails
    baseline/chat/<CODE>-change-requests.txt chat group exports
    baseline/spreadsheet/change-log.xlsx     the shared change log (and a CSV copy)
    baseline/shared-drive/<CODE>/<REF> .../  the shared drive folders

The four problem patterns (Section 2.1.3) are injected only where the scenario
marks a request with them:

    P1 unclear ownership   handovers don't name the next approver; the log's "With" column is blank or wrong
    P2 status divergence   the log shows an out-of-date status; chat may claim a different one
    P3 version confusion   documents are "on the drive" instead of attached, beside misleading copies
    P4 lost rationale      a decision's reason is missing from email and the log ("discussed on the call")
"""
import csv
import html
import mailbox
import random
import re
import shutil
import zipfile
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .scenario import DOMAIN, PROJECTS, STAGES

STATE_LABEL = {
    "APPROVED": "Approved", "REJECTED": "Rejected", "CHANGES_REQUESTED": "Changes requested",
    "CANCELLED": "Cancelled", "DRAFT": "Not submitted",
}


def _dl(code):
    return f"{code.lower()}-changes@{DOMAIN}"


def _slug(text, n=40):
    """A folder-safe title, cut at a word boundary."""
    keep = "".join(ch if ch.isalnum() or ch in " -" else "" for ch in text).strip()
    if len(keep) <= n:
        return keep
    return keep[:n].rsplit(" ", 1)[0].strip()


def _normalise_zip(path, date_time):
    """Rewrite a zip (an .xlsx) with fixed entry timestamps so it is byte-for-byte reproducible."""
    with zipfile.ZipFile(path) as source:
        entries = [(info.filename, source.read(info.filename)) for info in source.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries:
            if name == "docProps/core.xml":  # openpyxl stamps "modified" with the save time
                stamp = "%04d-%02d-%02dT%02d:%02d:%02dZ" % date_time
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>" + stamp.encode(), data)
            target.writestr(zipfile.ZipInfo(name, date_time=date_time), data, compress_type=zipfile.ZIP_DEFLATED)


class BaselineWriter:
    def __init__(self, scenario, out_dir):
        self.s = scenario
        self.out = Path(out_dir) / "baseline"
        self.rng = random.Random(scenario.seed + 1)
        self.emails = []            # (at, ref, EmailMessage, attachments[(name, bytes)])
        self.chats = {code: [] for code, _, _ in PROJECTS}
        self.rows = []
        self.notes = {}             # ref -> how each pattern was realised (for the ground truth)

    # ------------------------------------------------------------------ helpers

    def name(self, key):
        return self.s.person(key).name

    def addr(self, key):
        p = self.s.person(key)
        return f"{p.name} <{p.email}>"

    def approver(self, story, stage):
        return self.s.roles[story.project][STAGES[stage - 1][1]]

    def email(self, story, at, sender, to, subject, body, attachments=(), reply_to_first=True):
        msg = EmailMessage()
        msg["From"] = self.addr(sender)
        msg["To"] = ", ".join(self.addr(k) for k in to)
        msg["Cc"] = _dl(story.project)
        msg["Date"] = format_datetime(at)
        n = sum(1 for e in self.emails if e[1] == story.ref)
        msg["Message-ID"] = f"<{story.ref.lower()}.{n + 1}@{DOMAIN}>"
        if n and reply_to_first:
            msg["In-Reply-To"] = f"<{story.ref.lower()}.1@{DOMAIN}>"
            msg["References"] = f"<{story.ref.lower()}.1@{DOMAIN}>"
        msg["Subject"] = subject
        msg.set_content(body + "\n\n--\nZenkora Technologies Limited (fictional organisation; synthetic data)\n")
        for filename, content in attachments:
            msg.add_attachment(content, maintype="text", subtype="markdown", filename=filename)
        if attachments:
            msg.set_boundary(f"==flowbridge-{story.ref.lower()}-{n + 1}==")  # fixed, so the mbox is reproducible
        self.emails.append((at, story.ref, msg, list(attachments)))

    def chat(self, story, at, author, text):
        self.chats[story.project].append((at, self.name(author), text))

    # ------------------------------------------------------------------ one request

    def render_story(self, story):
        p, rng = story.patterns, self.rng
        roles = self.s.roles[story.project]
        notes = self.notes.setdefault(story.ref, {})
        subject = f"[{story.ref}] Change request: {story.title}"
        last_reason_note = ""

        for cycle in story.cycles:
            files = [(v.filename, v.content) for v in cycle.docs]
            if cycle.number == 1:
                if "P3" in p:
                    body = (f"Hi {self.name(roles['pm']).split()[0]},\n\nPlease review this change.\n\n"
                            f"{story.description}\n\nThe documents are in the shared drive folder for {story.ref}.")
                    self.email(story, cycle.submitted_at, story.requester, [roles["pm"]], subject, body)
                else:
                    listing = "\n".join(f"- {name}" for name, _ in files)
                    body = (f"Hi {self.name(roles['pm']).split()[0]},\n\nPlease review this change.\n\n"
                            f"{story.description}\n\nAttached:\n{listing}")
                    self.email(story, cycle.submitted_at, story.requester, [roles["pm"]], subject, body, files)
            else:
                first = self.name(roles["pm"]).split()[0]
                if "P3" in p:
                    body = f"Hi {first},\n\nI've updated the documents on the drive. Please take another look."
                    self.email(story, cycle.submitted_at, story.requester, [roles["pm"]], f"RE: {subject}", body)
                else:
                    changed = [v for v in cycle.docs if v.number > 1]
                    listing = "\n".join(f"- {v.filename}" for v in changed)
                    body = f"Hi {first},\n\nI've addressed the comments. Updated document attached:\n{listing}"
                    self.email(story, cycle.submitted_at, story.requester, [roles["pm"]], f"RE: {subject}", body,
                               [(v.filename, v.content) for v in changed])

            for decision in cycle.decisions:
                who = decision.approver
                has_next = decision.outcome == "APPROVE" and decision.stage < 3
                next_key = self.approver(story, decision.stage + 1) if has_next else None
                if decision.outcome == "APPROVE":
                    note = f" {decision.reason}" if decision.reason and "P4" not in p else ""
                    if has_next:
                        handover = ("Passing it along." if "P1" in p else
                                    f"Over to {self.name(next_key)} for {STAGES[decision.stage][0].lower()}.")
                    else:
                        handover = "Good to go." if decision.stage == 3 else ""
                    if rng.random() < 0.6:
                        to = [story.requester] + ([next_key] if next_key and "P1" not in p else [])
                        self.email(story, decision.at, who, to, f"RE: {subject}", f"Approved.{note} {handover}".strip())
                    else:
                        self.chat(story, decision.at, who, f"{story.ref} approved from my side.{note} {handover}".strip())
                    if decision.reason and "P4" not in p:
                        last_reason_note = decision.reason
                else:
                    verb = "can't approve" if decision.outcome == "REJECT" else "need some changes before I approve"
                    if "P4" in p:
                        where = rng.choice(["call", "chat"])
                        notes.setdefault("P4", []).append({"cycle": cycle.number, "stage": decision.stage,
                                                           "reason_location": where})
                        self.email(story, decision.at, who, [story.requester], f"RE: {subject}",
                                   f"I {verb} this one. We went through my comments on the call.")
                        if where == "chat":
                            self.chat(story, decision.at, who, f"For {story.ref}: {decision.reason.lower()}")
                    else:
                        self.email(story, decision.at, who, [story.requester], f"RE: {subject}",
                                   f"I {verb} this one.\n\nReason: {decision.reason}")
                        last_reason_note = decision.reason

        for author, text, at in story.comments:
            self.chat(story, at, author, f"{story.ref}: {text}")

        if story.withdrawn:
            actor, reason, at, before = story.withdrawn
            if before != "DRAFT":
                self.email(story, at, actor, [roles["pm"] if actor != roles["pm"] else story.requester],
                           f"RE: {subject}", f"Please close this request. {reason}")

        # Open requests attract chasers in the chat group.
        if story.state == "IN_REVIEW":
            waiting = self.approver(story, story.cycles[-1].waiting_stage)
            at = story.events_end()
            if "P1" in p:
                previous = self.approver(story, max(1, story.cycles[-1].waiting_stage - 1))
                self.chat(story, at, story.requester, f"Who has {story.ref} now? Not sure it's moved.")
                self.chat(story, at, roles["pm"], f"I think {self.name(previous)} still has it.")
                notes["P1"] = {"wrong_owner_named": self.name(previous)}
            else:
                self.chat(story, at, story.requester, f"@{self.name(waiting)} gentle reminder on {story.ref} 🙏")

        self.rows.append(self._log_row(story, last_reason_note, notes))
        self._drive(story, notes)

    def _true_status(self, story):
        if story.state == "IN_REVIEW":
            return f"Awaiting {STAGES[story.cycles[-1].waiting_stage - 1][0].lower()}"
        return STATE_LABEL[story.state]

    def _true_owner(self, story):
        if story.state == "IN_REVIEW":
            return self.name(self.approver(story, story.cycles[-1].waiting_stage))
        if story.state in ("CHANGES_REQUESTED", "DRAFT"):
            return self.name(story.requester)
        return ""

    def _log_row(self, story, reason_note, notes):
        status, owner = self._true_status(story), self._true_owner(story)
        last = story.events_end()
        if "P2" in story.patterns:
            stale = self._stale_status(story)
            notes["P2"] = {"log_status": stale, "true_status": status}
            if self.rng.random() < 0.5 and story.state != "APPROVED":
                claim_at = last
                self.chat(story, claim_at, self.s.roles[story.project]["pm"], f"{story.ref} is approved now I believe 👍")
                notes["P2"]["chat_claim"] = "Approved"
            status = stale
            last = story.cycles[0].submitted_at if story.cycles else story.raised_at
        if "P1" in story.patterns:
            wrong = self.rng.choice(["", "TBC", self.name(story.requester)])
            notes.setdefault("P1", {})["log_owner"] = wrong
            owner = wrong
        note = "" if "P4" in story.patterns else reason_note
        return [story.ref, story.title, self.name(story.requester), story.raised_at.strftime("%d/%m/%Y"),
                status, owner, last.strftime("%d/%m/%Y"), note]

    def _stale_status(self, story):
        """The status the log showed after the first submission, never updated since."""
        first = story.cycles[0]
        if first.decisions and first.decisions[0].outcome == "APPROVE" and len(first.decisions) > 1:
            return f"Awaiting {STAGES[1][0].lower()}"
        return f"Awaiting {STAGES[0][0].lower()}"

    def _drive(self, story, notes):
        folder = self.out / "shared-drive" / story.project / f"{story.ref} {_slug(story.title)}"
        folder.mkdir(parents=True, exist_ok=True)
        for v in story.versions:
            (folder / v.filename).write_bytes(v.content)
        if "P3" in story.patterns:
            decoys = []
            by_doc = {}
            for v in story.versions:
                by_doc.setdefault(v.doc, []).append(v)
            for doc, versions in by_doc.items():
                if len(versions) < 2:
                    continue
                oldest, latest = versions[0], versions[-1]
                decoys.append((f"{doc}_FINAL.md", oldest))                 # "final" that is actually version 1
                decoys.append((f"{doc} (1).md", latest))                   # a duplicate download
                decoys.append((f"{doc}_final_reviewed.md", versions[-2]))  # not what the last cycle reviewed
            for filename, version in decoys:
                (folder / filename).write_bytes(version.content)
            notes["P3"] = {"decoys": {name: f"v{v.number}" for name, v in decoys}}

    # ------------------------------------------------------------------ output

    def write(self):
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        for story in self.s.stories:
            self.render_story(story)
        self._write_mail()
        self._write_chat()
        self._write_log()
        self._write_readme()
        return self.notes

    def _write_mail(self):
        mail_dir = self.out / "mail"
        att_dir = mail_dir / "attachments"
        att_dir.mkdir(parents=True)
        box = mailbox.mbox(str(mail_dir / "ztl-change-requests.mbox"), create=True)
        box.lock()
        ordered = sorted(self.emails, key=lambda e: (e[0], e[1]))
        for at, _, msg, _ in ordered:
            envelope = mailbox.mboxMessage(msg)
            # A fixed envelope line keeps the mbox byte-for-byte reproducible from the seed.
            envelope.set_from(msg["From"].split("<")[-1].rstrip(">"), at.utctimetuple())
            box.add(envelope)
        box.flush()
        box.unlock()

        threads = {}
        for at, ref, msg, files in ordered:
            threads.setdefault(ref, []).append((at, msg, files))
        parts = []
        for ref, items in sorted(threads.items(), key=lambda kv: kv[1][-1][0], reverse=True):
            first = items[0][1]
            entries = []
            for i, (at, msg, files) in enumerate(items, start=1):
                links = []
                for filename, content in files:
                    target = att_dir / ref / f"{i}-{filename}"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    links.append(f'<a href="attachments/{ref}/{i}-{html.escape(filename)}">{html.escape(filename)}</a>')
                body = msg.get_body(preferencelist=("plain",)).get_content()
                entries.append(
                    f'<article class="msg"><header><strong>{html.escape(msg["From"])}</strong>'
                    f'<span>{at:%a %d %b %Y, %H:%M}</span></header>'
                    f'<div class="meta">To: {html.escape(msg["To"])} · Cc: {html.escape(msg["Cc"])}</div>'
                    f'<pre>{html.escape(body)}</pre>'
                    + (f'<div class="att">Attachments: {", ".join(links)}</div>' if links else "")
                    + "</article>"
                )
            parts.append(
                f'<details class="thread" data-text="{html.escape((first["Subject"] + " " + ref).lower())}">'
                f'<summary><span class="subj">{html.escape(first["Subject"])}</span>'
                f'<span class="count">{len(items)} message{"s" if len(items) > 1 else ""} · last '
                f'{items[-1][0]:%d %b %Y}</span></summary>{"".join(entries)}</details>'
            )
        page = INBOX_TEMPLATE.replace("{{THREADS}}", "\n".join(parts)).replace("{{COUNT}}", str(len(ordered)))
        (mail_dir / "inbox.html").write_text(page, encoding="utf-8")

    def _write_chat(self):
        chat_dir = self.out / "chat"
        chat_dir.mkdir(parents=True)
        for code, lines in self.chats.items():
            lines.sort(key=lambda x: x[0])
            text = "\n".join(f"[{at:%d/%m/%Y, %H:%M}] {who}: {msg}" for at, who, msg in lines)
            header = (f"ZTL {code} change requests (chat export)\n"
                      "Fictional organisation; synthetic messages.\n\n")
            (chat_dir / f"{code}-change-requests.txt").write_text(header + text + "\n", encoding="utf-8")

    def _write_log(self):
        sheet_dir = self.out / "spreadsheet"
        sheet_dir.mkdir(parents=True)
        header = ["Ref", "Title", "Requester", "Raised", "Status", "With", "Last update", "Notes"]
        book = Workbook()
        book.remove(book.active)
        for code, name, _ in PROJECTS:
            ws = book.create_sheet(code)
            ws.append(header)
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="D9D9D9")
            for row in self.rows:
                if row[0].startswith(code + "-"):
                    ws.append(row)
            for i, width in enumerate([10, 48, 22, 11, 32, 22, 12, 50], start=1):
                ws.column_dimensions[get_column_letter(i)].width = width
            ws.freeze_panes = "A2"
        stamp = self.s.anchor.replace(tzinfo=None)
        book.properties.creator = "ZTL change log (synthetic)"
        book.properties.created = book.properties.modified = stamp
        target = sheet_dir / "change-log.xlsx"
        book.save(target)
        _normalise_zip(target, stamp.timetuple()[:6])
        with open(sheet_dir / "change-log.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(self.rows)

    def _write_readme(self):
        (self.out / "README.md").write_text(BASELINE_README, encoding="utf-8")


BASELINE_README = """# ZTL baseline sandbox (manual process)

This folder is the baseline condition for the evaluation: how a team at the fictional firm
Zenkora Technologies Limited (ZTL) handles change approvals without Flowbridge.

- `mail/inbox.html`: open in a browser to read the team's change-request emails (search box at the top).
  The same emails are in `mail/ztl-change-requests.mbox` for any mail client.
- `chat/`: exports of each project's chat group.
- `spreadsheet/change-log.xlsx`: the shared change log, one sheet per project.
- `shared-drive/`: the shared drive, one folder per request.

Everything here is synthetic. ZTL is not a real company.
"""

INBOX_TEMPLATE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZTL mail: change requests</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f4f5f7;color:#1f2937}
header.top{background:#1e3a5f;color:#fff;padding:12px 20px}
header.top h1{font-size:18px;margin:0}
.bar{padding:12px 20px;background:#fff;border-bottom:1px solid #ddd;position:sticky;top:0}
.bar input{width:100%;max-width:520px;padding:8px;font-size:15px}
main{padding:12px 20px;max-width:1000px}
.thread{background:#fff;border:1px solid #ddd;border-radius:6px;margin-bottom:8px}
.thread summary{padding:10px 12px;cursor:pointer;display:flex;justify-content:space-between;gap:12px}
.subj{font-weight:600}.count{color:#6b7280;font-size:13px;white-space:nowrap}
.msg{border-top:1px solid #eee;padding:10px 14px}.msg header{display:flex;justify-content:space-between;gap:8px}
.meta{color:#6b7280;font-size:12px;margin:4px 0}pre{white-space:pre-wrap;font-family:inherit;margin:6px 0}
.att{font-size:13px}.note{color:#7a4b00;font-size:13px}
</style></head><body>
<header class="top"><h1>ZTL mail · change requests ({{COUNT}} messages)</h1>
<div class="note" style="color:#ffe6b3">Fictional organisation. Synthetic data for an evaluation study.</div></header>
<div class="bar"><label for="q">Search subject or reference</label><br>
<input id="q" type="search" placeholder="e.g. LND-017 or rate limiting" autocomplete="off"></div>
<main id="threads">
{{THREADS}}
</main>
<script>
document.getElementById('q').addEventListener('input', function (e) {
  var q = e.target.value.trim().toLowerCase();
  document.querySelectorAll('.thread').forEach(function (t) {
    t.style.display = !q || t.dataset.text.indexOf(q) !== -1 ? '' : 'none';
  });
});
</script></body></html>
"""
