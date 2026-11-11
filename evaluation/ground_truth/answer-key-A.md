# Answer key, scenario set A (scoring only; do not show participants)

Persona: Ozioma Nwachukwu (ozioma.nwachukwu@ztl.example), requester on LND.

**T1.** Success if the request reaches the project manager (Nasiru Lawal)
for review with: the title, the purpose, the risk, the rollback, and the design note `loan-limit-check-design-note.md` attached.
Flowbridge: the request is submitted and stage 1 is active. Baseline: an email to the PM (copying
lnd-changes@ztl.example) with the attachment, plus a row in the change log.

**T2.** LND-017: **In review, awaiting technical lead review**. Next to act: **Simon Ogunleye**.
Score status and person separately (retrieval accuracy: 2 answers). Baseline traps: P1 and P2
(the log shows an out-of-date status and owner).

**T3.** LND-019: success if version 2 of the design note (`T3-design-note_v2.md`,
SHA-256 b5a4ed76acbb06c4…) is attached and the request is sent back for review. Flowbridge: resubmitted as
revision 2, cycle 2 at stage 1. Baseline: a reply to the
thread with the attachment, addressed to the PM or to Simon Ogunleye.

**T4.** LND-008, final approval by Ayoka Makinwa (cycle 2,
stage 3). Approved versions:
   - Rollback plan: version 2 (`rollback-plan_v2.md`, SHA-256 8eca8469952845a3…)
   - Design note: version 1 (`design-note.md`, SHA-256 9c0a5bb1971e7057…)
Score each document separately (retrieval accuracy). Baseline trap: P3 (misleading copies on the drive).

**T5.** LND-003, 6 decisions:
   1. Cycle 1, stage 1 (Project manager review): Nasiru Lawal: Approved
   2. Cycle 1, stage 2 (Technical lead review): Simon Ogunleye: Approved
   3. Cycle 1, stage 3 (Product owner sign-off): Ayoka Makinwa: Changes requested — "Confirm the data retention period with the client."
   4. Cycle 2, stage 1 (Project manager review): Nasiru Lawal: Approved
   5. Cycle 2, stage 2 (Technical lead review): Simon Ogunleye: Approved — "Looks good."
   6. Cycle 2, stage 3 (Product owner sign-off): Ayoka Makinwa: Approved
Score: decisions listed correctly and in order, out of 6
(reconstruction accuracy); and separately, whether the reason for the request for changes was recovered.
Baseline trap: P4 (that reason is missing from email and the log).
