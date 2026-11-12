"""Keystroke-Level Model (KLM) predictions for the evaluation tasks T1 to T5.

This is an analytical evaluation, not an observation of users. It predicts how long an
expert who makes no errors would take to carry out each task in each condition
(Card et al., 1980; Kieras, 2001). Time spent reading is added at an average silent
reading rate (Brysbaert, 2019), because the baseline tasks are mostly reading.

Reading loads are measured, not estimated:
- baseline: the words in the emails, chat lines and change-log rows an expert must read,
  counted from the generated baseline files (evaluation/baseline);
- Flowbridge: the words in the page regions an expert must read, measured on the
  evaluation build with the evaluation dataset loaded (FLOWBRIDGE_READING below).

Assumptions favour the baseline wherever there is doubt: the baseline expert knows which
channels to check, uses search in every tool, and is never misled by the injected problem
patterns. The model therefore predicts lower bounds for the baseline.

Run from the repository root:  python evaluation/klm/klm_model.py
"""
import csv
import email
import mailbox
import re
from email import policy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "evaluation" / "baseline"
OUT = Path(__file__).resolve().parent

# Operator times in seconds (Card et al., 1980; Kieras, 2001)
OPS = {"K": 0.28, "P": 1.10, "B": 0.10, "H": 0.40, "M": 1.35, "R_PAGE": 0.5, "R_FILE": 0.5}
READING_WPM = 238  # Brysbaert (2019), English non-fiction
SENSITIVITY = {"fast": {"K": 0.20, "wpm": 300}, "slow": {"K": 0.28, "wpm": 200}}

SETS = {
    "A": {"project": "LND", "persona": "Ozioma Nwachukwu", "pm": "nasiru.lawal@ztl.example", "pm_first": "Nasiru",
          "pm_name": "Nasiru Lawal", "cc": "lnd-changes@ztl.example", "next_ref": "LND-021",
          "title": "Add a maximum loan amount check to the loan application form",
          "body": "Purpose: Reject applications above the product's maximum loan amount before credit scoring. "
                  "Risk: Low; rollback by switching the feature flag off.",
          "T2": "LND-017", "T3": "LND-019", "T3_reviewer": "Simon", "T4": "LND-008", "T5": "LND-003"},
    "B": {"project": "TEL", "persona": "Blessing Adetokunbo", "pm": "ololade.oyetoro@ztl.example", "pm_first": "Ololade",
          "pm_name": "Ololade Oyetoro", "cc": "tel-changes@ztl.example", "next_ref": "TEL-021",
          "title": "Add a daily spend cap to the airtime top-up API",
          "body": "Purpose: Reject top-ups that would take a subscriber over the daily spend cap. "
                  "Risk: Low; rollback by switching the feature flag off.",
          "T2": "TEL-018", "T3": "TEL-014", "T3_reviewer": "Okechukwu", "T4": "TEL-005", "T5": "TEL-003"},
}

# Words read in Flowbridge, measured on the evaluation build (12 November 2026):
#   status strip (T2, T3), latest decision row (T3), final cycle header, the "Evidence reviewed"
#   lines and the final decision line (T4), and the decision record table (T5).
FLOWBRIDGE_READING = {
    "A": {"T2": 19, "T3": 11 + 23, "T4": 31, "T5": 105},
    "B": {"T2": 19, "T3": 11 + 20, "T4": 30, "T5": 121},
}
HEADER_WORDS_PER_EMAIL = 4  # sender name and date the reader must take in


def words(text):
    return len(re.findall(r"[A-Za-z0-9][\w'’.\-:/@]*", text))


def load_baseline():
    messages = []
    for raw in mailbox.mbox(BASELINE / "mail" / "ztl-change-requests.mbox"):
        msg = email.message_from_bytes(raw.as_bytes(), policy=policy.default)
        body = msg.get_body(preferencelist=("plain",))
        text = body.get_content() if body else ""
        text = text.split("\n--\n")[0]  # the signature is skipped, not read
        messages.append({"subject": msg["subject"] or "", "words": words(text) + HEADER_WORDS_PER_EMAIL})
    chats = {p.stem.split("-")[0]: p.read_text().splitlines() for p in (BASELINE / "chat").glob("*.txt")}
    log = list(csv.DictReader(open(BASELINE / "spreadsheet" / "change-log.csv", newline="")))
    return messages, chats, log


class Sequence:
    """Accumulates KLM operators and reading for one task in one condition."""

    def __init__(self):
        self.ops = {"K": 0, "P": 0, "B": 0, "H": 0, "M": 0, "R_PAGE": 0, "R_FILE": 0}
        self.read_words = 0

    def add(self, op, n=1):
        self.ops[op] += n
        return self

    # building blocks
    def think(self, n=1): return self.add("M", n)
    def click(self): return self.add("P").add("B", 2)
    def double_click(self): return self.add("P").add("B", 4)
    def keys(self, n): return self.add("H").add("K", n).add("H")
    def type_field(self, text):  # decide, point at the field, click, type
        return self.think().click().keys(len(text))
    def page(self): return self.add("R_PAGE")
    def open_file(self): return self.add("R_FILE")
    def read(self, n): self.read_words += n; return self

    def pick_file(self):  # system file dialog: open the materials folder, select the file, Open
        return self.think().double_click().click().click().open_file()

    def find_in_app(self, ref):  # Ctrl+F, type the reference, Enter
        return self.think().keys(2 + len(ref) + 1)

    def seconds(self, k=None, wpm=None):
        k = OPS["K"] if k is None else k
        wpm = READING_WPM if wpm is None else wpm
        t = sum(OPS[o] * n for o, n in self.ops.items() if o != "K") + k * self.ops["K"]
        return t + self.read_words * 60 / wpm


def baseline_tasks(s, data):
    messages, chats, log = data
    thread = lambda ref: [m for m in messages if ref in m["subject"]]
    chat_words = lambda ref: sum(words(l) for l in chats[s["project"]] if ref in l)
    row_words = lambda ref: sum(words(" ".join(v or "" for v in r.values())) for r in log if r["Ref"] == ref)
    tasks = {}

    def search_and_read_thread(q, ref):
        q.think().click().keys(len(ref))          # search box in the inbox viewer
        for m in thread(ref):
            q.click().read(m["words"])           # open each message and read it
        return q.think()

    # T1: change-log row, then the email to the project manager with the attachment
    q = Sequence()
    q.click().open_file().click()                 # open the change log, choose the project sheet
    q.think().keys(2).read(3).think()             # Ctrl+End, read the last reference, work out the next
    q.click()
    for value in [s["next_ref"], s["title"], s["persona"], "12/11/2026", "Awaiting project manager review", s["pm_name"], "12/11/2026"]:
        q.think().keys(len(value) + 1)            # each cell, then Tab
    q.keys(2)                                     # Ctrl+S
    q.click().think()                             # new email
    q.type_field(s["pm"]).type_field(s["cc"])
    q.type_field(f"[{s['next_ref']}] Change request: {s['title']}")
    q.type_field(f"Hi {s['pm_first']},\n\nPlease review this change.\n\n{s['body']}\n")
    q.think().click().pick_file()                 # attach the design note
    q.think().click().page()                      # send
    tasks["T1"] = q

    # T2: status and next approver, reconciled across email, chat and the log
    q = search_and_read_thread(Sequence(), s["T2"])
    q.click().find_in_app(s["T2"]).read(chat_words(s["T2"])).think()
    q.click().find_in_app(s["T2"]).read(row_words(s["T2"])).think()
    tasks["T2"] = q.think()

    # T3: read the request for changes, reply with version 2, update the log
    q = search_and_read_thread(Sequence(), s["T3"])
    q.click().think()                             # reply
    q.type_field(f"Hi {s['T3_reviewer']},\n\nI have revised the document as requested. Version 2 is attached.\n")
    q.think().click().pick_file()
    q.think().click().page()                      # send
    q.click().find_in_app(s["T3"]).read(row_words(s["T3"]))
    for value in ["Awaiting project manager review", s["pm_name"], "12/11/2026"]:
        q.think().click().keys(len(value) + 1)
    q.keys(2)
    tasks["T3"] = q

    # T4: which version of each document was approved, from email, chat and the shared drive
    q = search_and_read_thread(Sequence(), s["T4"])
    q.click().find_in_app(s["T4"]).read(chat_words(s["T4"])).think()
    folder = next((BASELINE / "shared-drive" / s["project"]).glob(f"{s['T4']} *"))
    q.click().double_click().open_file().double_click().open_file()
    q.read(sum(words(p.name.replace("_", " ")) for p in folder.iterdir())).think(2)  # compare names, decide
    tasks["T4"] = q

    # T5: every decision, in order, with its reason
    q = search_and_read_thread(Sequence(), s["T5"])
    q.click().find_in_app(s["T5"]).read(chat_words(s["T5"]))
    tasks["T5"] = q.think(6)                      # one decision identified per M
    return tasks


def flowbridge_tasks(s, set_name):
    reading = FLOWBRIDGE_READING[set_name]
    tasks = {}

    def open_request(q, ref):  # project page, filter by reference, open the request
        return q.think().click().page().type_field(ref).keys(1).page().click().page()

    q = Sequence()
    q.think().click().page()                      # open the project
    q.click().page()                              # New change request
    q.type_field(s["title"]).type_field(s["body"])
    q.think().click().pick_file()
    q.think().click().page()                      # Save and submit for review
    tasks["T1"] = q

    tasks["T2"] = open_request(Sequence(), s["T2"]).read(reading["T2"]).think()

    q = open_request(Sequence(), s["T3"]).read(reading["T3"]).think()
    q.think().click().pick_file()
    q.think().read(5)                             # check the upload goes to the right document
    q.click().page()                              # Upload
    q.think().click().page()                      # Resubmit
    tasks["T3"] = q

    q = open_request(Sequence(), s["T4"])
    q.keys(2).read(reading["T4"]).think(2)        # Page Down to the final cycle, read, decide
    tasks["T4"] = q

    q = open_request(Sequence(), s["T5"]).read(reading["T5"])
    tasks["T5"] = q.think(6)
    return tasks


def main():
    data = load_baseline()
    rows = []
    for set_name, s in SETS.items():
        base, flow = baseline_tasks(s, data), flowbridge_tasks(s, set_name)
        for t in ["T1", "T2", "T3", "T4", "T5"]:
            for cond, q in (("Baseline", base[t]), ("Flowbridge", flow[t])):
                rows.append({
                    "set": set_name, "task": t, "condition": cond,
                    **{f"n_{o}": n for o, n in q.ops.items()}, "words_read": q.read_words,
                    "seconds": round(q.seconds(), 1),
                    "seconds_fast": round(q.seconds(SENSITIVITY["fast"]["K"], SENSITIVITY["fast"]["wpm"]), 1),
                    "seconds_slow": round(q.seconds(SENSITIVITY["slow"]["K"], SENSITIVITY["slow"]["wpm"]), 1),
                })
    with open(OUT / "klm_predictions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"{'task':4} {'set':3} {'baseline':>9} {'flowbridge':>10} {'words b/f':>10}")
    for set_name in SETS:
        for t in ["T1", "T2", "T3", "T4", "T5"]:
            b = next(r for r in rows if r["set"] == set_name and r["task"] == t and r["condition"] == "Baseline")
            f = next(r for r in rows if r["set"] == set_name and r["task"] == t and r["condition"] == "Flowbridge")
            print(f"{t:4} {set_name:3} {b['seconds']:9.1f} {f['seconds']:10.1f} {b['words_read']:5}/{f['words_read']}")


if __name__ == "__main__":
    main()
