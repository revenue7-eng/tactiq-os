# Contributing

Thank you for looking at this repository.

This document describes what a useful contribution looks like here and
how claims are expected to be worded. Most of it is about evidence
rather than formatting.

---

## Scope

`meta-tactiq` is a Yocto layer: distro configuration, machine
configurations, image recipes, kernel configuration, the A/B update
setup, and packaging for the attestation agent. `README.md` lists what
each directory holds; `DESIGN_PRINCIPLES.md` gives the per-domain
rationale, including what is tracked but not yet shipped.

SELinux policy lives in a separate repository and is consumed as a
layer.

Out of scope: application-layer software, cloud services, model
training. Issues about those will be closed as out of scope, without
prejudice.

---

## Before you open an issue

State what you observed, on which machine, from which image, and how to
reproduce it. A report that cannot be reproduced cannot be fixed.

Supported machines are `tactiq-qemu-x86`, `tactiq-rock5a`,
`tactiq-rock5b`, `tactiq-rock5t` and `tactiq-generic-arm64`. If the
behaviour reproduces under `tactiq-qemu-x86`, say so — it makes the
report far easier to act on, since it removes the board from the
picture.

Images: `tactiq-image` is the production profile, `tactiq-image-dev`
adds development conveniences. Say which one you built. Behaviour
differs between them by design, and a report against the wrong one
sends everyone looking in the wrong place.

Include the command you ran and its full output. A paraphrase of an
output is not an output.

### Security issues

Do not open a public issue for a vulnerability. See `SECURITY.md`.

---

## Building and checking

`README.md`, section Build, points at `scripts/run-qemu.sh` for the
reference local workflow. That file is the source of truth for build
steps; this document does not repeat them, so that the two cannot
drift apart.

Checks that are much cheaper than a full image and worth running while
you iterate:

- SELinux policy syntax: `bitbake refpolicy-targeted -c compile`
- Policy linking: build the full policy target
- Variable resolution: `bitbake-getvar --value <VAR>`

Run `bitbake-getvar` once per command. Two of them joined with `;` on
one line will break the connection to the server.

One caution about incremental builds: after editing a recipe, a result
reporting that nearly every task did not need to be rerun means the
build did not see your change. A real change shifts hashes and
triggers a cascade.

---

## Pull requests

Fetch first, then branch from the current head of the default branch.
Open a pull request; do not push to the default branch directly.

One change per pull request. A change that touches policy, recipes and
documentation at once is three reviews at the same time, and will take
longer than three separate pull requests would.

The description says what changed and what was run to check it. If
nothing was run, say so. An unverified change is acceptable; an
unverified change described as verified is not.

Reviewers are assigned from `CODEOWNERS`.

### Patches sent as files

Patches are applied with `git am`, which refuses loudly when the tree
has diverged. Do not paste patch text into an issue or a comment:
blank lines are lost in transit, and the result can apply cleanly while
being wrong.

---

## How claims are worded

This applies to commit messages, pull request descriptions, comments in
recipes and policy, documentation, and measurement reports. It is the
part of this document we actually care about.

### Evidence travels with the claim

A statement about state carries what confirms it: a path, a command, an
output, a hash. Without that, there is no statement.

Not this:

> Denial fixed, verified.

This:

> Rule added in `tactiq_agent.te`. On hardware: `dmesg | grep -c cert_t`
> returns 0, against 16 on the previous policy version. Log and hash in
> `measurements/SHA256SUMS`.

### Numbers instead of adverbs

"Significantly", "much", "noticeably" mean nobody measured. If it was
measured, give the number and the conditions. If it was not, say it was
not.

Not this:

> Boot is noticeably faster.

This:

> 11.2 s against 14.8 s on the previous image, three runs, cold start,
> same slot.

### Negative statements need full coverage

"This does not exist in the tree" is said after `grep -Rn` from the
layer root, or `bitbake-getvar`, or `/proc/config.gz`. Otherwise the
correct wording is "it is not in this output; I will check".

### A document is not the state of the tree

"Supported", "implemented", "validated" are checked before they are
written. If no check was made, write "not established".

"Closed" means the defect is absent from the tree and this was
confirmed by a run. Written but never run is not closed.

### Say what the system did

Systems do not think, decide, trust, or get surprised. Describe the
mechanism. A metaphor works aloud and fails in a document someone will
act on.

### Keep identifiers intact

Type names, recipe names, machine names, filesystem types: these carry
the meaning. Do not paraphrase them into prose — the paraphrase is less
precise, not more readable.

### Section headings name their contents

Not "the important part" or "what actually matters". A reader scanning
for something needs the heading to say what is there.

### Delete the closing flourish

A short line at the end of a section asserting a general truth is
decoration. Remove it and check whether anything was lost. Usually
nothing was.

---

## Measurement reports

Reports go in `measurements/`, in the repository whose object was
measured — policy measurements belong with the policy layer.

Naming follows what is already there: `<topic>-<YYYYMMDD>.md` for the
report, raw logs as `.log` with a run suffix when there is more than
one run. Logs live in `measurements/logs/`, and their hashes go in
`measurements/SHA256SUMS`.

A report states what was measured, on which machine and image, the
exact commands, the raw output, and the conditions under which the
numbers hold. Conditions are part of the number, not a footnote: a
figure quoted without its conditions is a different figure.

If a result is ambiguous, the report says so. A report that explains
away its own anomaly is worth less than one that records it.

---

## License

MIT. See `LICENSE`. By contributing you agree that your contribution is
licensed under the same terms.
