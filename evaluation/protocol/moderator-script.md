# Moderator script

About 60 minutes per participant. Read the words in quotation marks as written, so every session is the same.

## 1. Welcome and consent (5 min)

"Thank you for taking part. This study compares two ways of handling approvals for IT changes. The company
in the tasks, Zenkora Technologies Limited, is fictional, and everything you will see is made up. We are
testing the tools, not you. You can stop at any time without giving a reason."

- Check that the consent form is signed and give the participant code (for example P05).
- Start the screen recording.

## 2. Orientation (5 min)

Look up the participant's order in `session-orders.csv`. For each condition, show the sandbox for two minutes
without doing any task: where things are, nothing more.

## 3. First condition: five tasks (15 min)

"Here are five tasks. Please read each one aloud, then do it. Say 'done' when you have finished. If you get
stuck, say so. That is useful to us. I can't help with the tasks themselves."

- Start the timer when the participant finishes reading a task aloud. Stop it when they say "done" or "stuck".
- **Help rule:** if they ask for help, you may repeat the task wording only. Any other help ends the
  unassisted attempt. Record `help_given = 1` and `completed_unassisted = 0`, then let them finish.
- Write their answer for T2, T4 and T5 exactly as given.

## 4. Questionnaire for the first condition (5 min)

The System Usability Scale and the four perceived-visibility items, from `questionnaires.md`.

## 5. Second condition: five tasks, then the questionnaire (20 min)

Same as steps 3 and 4, with the other condition and the other scenario set.

## 6. Debrief (10 min)

Ask the debrief questions in `questionnaires.md`. Stop the recording. Thank the participant.

## After the session

- Enter the results in a copy of `results-template.csv`.
- Reset both sandboxes before the next participant.
- A second scorer independently scores at least 20 percent of answers (Section 3.1.4).
