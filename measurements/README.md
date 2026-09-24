# measurements

Each measurement in this directory is a report (`*.md`) and, where the
measurement produced output, the raw output the report was read from
(`*.log`, or files under `logs/`).

## Rules

1. Raw output is committed as produced and listed in `SHA256SUMS` in the
   same commit. The report is a reading of that output; the output is what a
   reader checks the reading against.
2. A report states the tree revision it ran against, the versions of the
   tools it used, and the board or host it ran on.
3. A report states what would make its result stop holding: the change to the
   tree, a tool or the hardware after which it has to be run again. The
   horizon is an event, not a date.
4. A negative test, one that expects a refusal, keeps the raw output of the
   refusal and of its control case. A refusal recorded only in the prose of a
   report is a claim about a refusal, not a record of one.
5. A result is not edited in place after the fact. A result that stops
   holding is superseded by a new report that names the one it replaces;
   a correction is made in its own commit that says what changed.

CI (`measurements-integrity` in `.github/workflows/ci.yml`) checks rule 1:
every sum still matches its file, and every `*.log` in this directory has a
sum. Rules 2 to 5 are checked in review.

## Known gaps

- `rim-signer-negative-20260922.md` has no raw output. Its refusals exist
  only as the table in the report. It is to be run again with the output
  kept (rule 4).
- Reports older than this file do not all state a revision or a horizon
  (rules 2 and 3). They are left as they are (rule 5) and get a successor
  when they are next run.
