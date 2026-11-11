# Evaluation protocol (Phase B: user acceptance test)

These materials run the comparison described in Section 3.1.4. Every participant does five matched tasks
in the manual baseline and five in Flowbridge, in one of four counterbalanced orders.

> Zenkora Technologies Limited (ZTL) is a fictional organisation. Tell every participant this before they start.
> All people, requests, messages and documents are synthetic.

**Before any session:** university ethics approval, the signed consent form, and a pilot with two or three people.

## Files

| File | Use |
|---|---|
| `session-orders.csv` | Which condition and scenario set each participant does first (four orders, balanced over 12 people) |
| `moderator-script.md` | What the moderator says and does, in order |
| `scoring-rubric.md` | How each task is timed and scored |
| `questionnaires.md` | SUS, the four perceived-visibility items and the debrief questions |
| `results-template.csv` | One row per participant per task |
| `../scenario-sets/A`, `../scenario-sets/B` | Task cards and the files participants need |
| `../ground_truth/answer-key-A.md`, `answer-key-B.md` | Correct answers (moderator and scorers only) |
| `../baseline/` | The manual-process sandbox |
| `../accounts.csv` | Every synthetic account; all passwords are `ztl-eval-2026` |

## Preparing the two conditions

**Flowbridge.**
1. Reset the system data before every participant, because tasks T1 and T3 change it:
   `python manage.py generate_evaluation_data --load --flush`. This takes about 30 seconds and always produces the same data.
2. Open a private browser window on the sign-in page.
3. Have the persona's email ready: set A is `ozioma.nwachukwu@ztl.example` and set B is
   `blessing.adetokunbo@ztl.example`.

**Baseline.**
1. Copy `evaluation/baseline/` to a fresh folder for each participant.
2. Open `mail/inbox.html` in the browser, the change log in a spreadsheet program, the chat export in a text
   editor, and the `shared-drive` folder in the file browser.
3. For T1 and T3 the participant writes their reply as a draft email (a plain text file in the folder is fine)
   and edits the change log copy.

Use the same screen, browser and recording set-up for both conditions.
