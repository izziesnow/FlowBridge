# Running the sessions remotely

The protocol in this folder works over a video call, with the participant sharing their screen.
Everything the participant needs is online. Nothing has to be installed except a browser and a program
that opens spreadsheets (Excel, LibreOffice or Google Sheets).

> Zenkora Technologies Limited (ZTL) is a fictional organisation, and all data are synthetic. Say so at the
> start of every session.

## What is where

| Item | Where |
|---|---|
| Flowbridge for the sessions | The `flowbridge-uat` copy on Render (see `docs/hosting.md`), not the demo copy |
| Participant downloads | `https://<sessions copy>/evaluation/files/`: the baseline sandbox and task materials for sets A and B. The answer keys are never offered. |
| Reset before each participant | `https://<sessions copy>/evaluation/reset/`. Sign in as `admin@ztl.example`, type RESET and wait one to three minutes. |
| Personas | Set A: `ozioma.nwachukwu@ztl.example`. Set B: `blessing.adetokunbo@ztl.example`. The password is the copy's `HOSTED_PASSWORD`. |
| Task wording, timer, scores and questionnaires | The session console (Prince's private page), which also stores the results |
| Answer keys | `../ground_truth/answer-key-A.md` and `-B.md`, for the moderator and scorers only. Do not share your screen while they are open. |

## Before the first session

1. Confirm ethics approval with your supervisor, as the protocol requires.
2. Run a pilot with two or three people and fix anything unclear in the wording.
3. Schedule 60 minutes per participant, on a call tool that can record (Zoom, Teams or Google Meet).

## Before each participant

1. Send the participant information and consent text from the session console, and get their written
   agreement in reply.
2. Reset the sessions copy, and wait until the reset page says the data are ready.
3. Open the participant's row in the session console. It shows their order from `session-orders.csv`.

## During the session

1. Start the recording once the participant agrees to it. Ask them to share their screen.
2. **Baseline condition.** Ask them to open `/evaluation/files/`, download `baseline.zip` and the materials
   for their set, and unzip both into new folders. They then open `mail/inbox.html` in their browser, the
   change log in their spreadsheet program, and the chat export and shared-drive folder in their file viewer.
   For T1 and T3 they write the email as a text file and edit their copy of the change log.
3. **Flowbridge condition.** They open the sessions copy in a private window, sign in as the persona for
   their set, and upload files from the materials folder.
4. Paste each task into the call chat from the console, start the timer when they finish reading it aloud,
   and stop it when they say "done" or "stuck". Apply the help rule in `moderator-script.md`.
5. After each condition, read the questionnaire items aloud from the console and record their answers.
   Alternatively, paste the items into the chat and let them reply with numbers.
6. Finish with the debrief questions.

## Afterwards

Score the answers against the answer key in the console. A second scorer rescores at least 20 percent
(see `scoring-rubric.md`). The console exports the results in the layout of `results-template.csv`.
