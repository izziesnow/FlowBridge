# Keystroke-Level Model predictions

This folder holds an **analytical evaluation**: predicted task times for an expert who makes no errors, worked out with the Keystroke-Level Model (KLM) of Card, Moran and Newell (1980). **These are predictions, not observations.** No participant took part, and the numbers must not be reported as user acceptance test results. The user study in `evaluation/protocol/` is still to be run.

## Files

| File | What it is |
|---|---|
| `klm_model.py` | The model: operator sequences for tasks T1 to T5 in both conditions and both scenario sets |
| `klm_predictions.csv` | Its output: operator counts, words read and predicted seconds per task, condition and set |
| `../../docs/figures/fig5-2-klm.png` | The chart used as Figure 5.2 in the report |

Run it from the repository root with `python evaluation/klm/klm_model.py`. It needs the generated baseline files in `evaluation/baseline/`.

## Method

Each task is written as a sequence of KLM operators, using the published operator times:

| Operator | Meaning | Time |
|---|---|---|
| K | Keystroke (average non-secretarial typist, about 40 words per minute) | 0.28 s |
| P | Point with the mouse | 1.10 s |
| B | Press or release the mouse button (a click is BB) | 0.10 s |
| H | Move the hand between mouse and keyboard | 0.40 s |
| M | Mental preparation, placed with Kieras's (2001) rules | 1.35 s |
| R | Waiting for a page or file to open | 0.5 s |

The KLM has no operator for reading, and the baseline tasks are mostly reading. Reading time is therefore added at 238 words per minute, the average silent reading rate for English non-fiction (Brysbaert, 2019). Reading loads are counted, not estimated: the baseline words come from the emails, chat lines, change-log rows and file names an expert must read; the Flowbridge words were measured on the page regions that answer each task.

### Assumptions that favour the baseline

- The expert knows which channels to check and searches each one by reference.
- The expert is never misled by the injected problem patterns (contradictory status, ambiguous file names, decisions made only in chat, a stale log).
- Email signatures are skipped, not read.
- Saving to the shared drive is left out of T1 and T3.

The baseline predictions are therefore lower bounds: a real user would also make errors, take wrong turns and re-read.

## Results (mean of sets A and B, seconds)

| Task | Baseline | Flowbridge | Reduction |
|---|---|---|---|
| T1 Submit a new change request | 182.2 | 77.7 | 57% |
| T2 Find status and next approver | 47.7 | 18.1 | 62% |
| T3 Respond to a request for changes | 112.0 | 37.6 | 66% |
| T4 Identify the approved versions | 80.4 | 23.7 | 71% |
| T5 Reconstruct the decision history | 67.2 | 48.5 | 28% |
| All five tasks | 489.6 | 205.6 | 58% |

**Sensitivity.** With a faster user (K = 0.20 s, reading at 300 words per minute) the totals are 406.9 s and 177.0 s (57% lower). With a slower reader (200 words per minute) they are 515.9 s and 215.2 s (58% lower).

## Limits

- The KLM predicts expert, error-free execution time to within about 21% (Card et al., 1980). It says nothing about learning, errors, accuracy or satisfaction.
- It does not model the search and recognition problems the baseline was built to contain, which the user study is designed to measure.
- The operator sequences are the author's own analysis and have not been checked against recordings of real use.

## References

Brysbaert, M. (2019). How many words do we read per minute? A review and meta-analysis of reading rate. *Journal of Memory and Language, 109*, 104047. https://doi.org/10.1016/j.jml.2019.104047

Card, S. K., Moran, T. P., & Newell, A. (1980). The keystroke-level model for user performance time with interactive systems. *Communications of the ACM, 23*(7), 396–410. https://doi.org/10.1145/358886.358895

Kieras, D. (2001). *Using the keystroke-level model to estimate execution times*. University of Michigan.
