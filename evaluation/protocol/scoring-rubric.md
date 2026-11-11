# Scoring rubric

Score against `ground_truth/answer-key-A.md` or `answer-key-B.md`, never from memory of the system.

## Measures

| Measure | How it is recorded |
|---|---|
| Task time | Seconds from finishing reading the task aloud to saying "done" or "stuck". From the recording. |
| Task success | 1 if the task is completed correctly without help (see the help rule), otherwise 0. |
| Retrieval accuracy | Correct answers divided by answers requested. T2 asks for 2 (status, next person). T4 asks for one per document. |
| Reconstruction accuracy | T5 only: decisions listed correctly and in the correct position, divided by the number of decisions in the key. |
| Reason recovered | T5 only: 1 if the reason for the request for changes is given correctly, otherwise 0. |

## Per task

- **T1.** Success needs all of the following:
  - the request reaches the right project manager for review;
  - it has the title, purpose, risk and rollback;
  - the design note is attached.

  In the baseline it must also be added to the change log.
- **T2.** One point for the status ("in review, awaiting technical lead review", or equivalent words). One point
  for the right person's name. "In review" alone, without the stage, still earns the status point.
- **T3.** Success needs the updated document attached as a new version and the request sent back for review.
  In Flowbridge, the request must be resubmitted. In the baseline, the reply must go to the PM or to the approver
  who asked for the changes, and attach the file.
- **T4.** One point per document named with the correct version. A version may be given as a number, a filename
  whose content is that version, or the checksum.
- **T5.** Score each decision in order. A decision is correct when the person, stage and outcome are all right.
  An extra decision that did not happen counts as an error but does not shift the others.

## Second scorer

Score at least 20 percent of all task answers twice, chosen at random across participants and conditions.
Report agreement as Cohen's kappa. Settle disagreements by discussion and keep the agreed score.
