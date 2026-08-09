# rc7 release assembly, 2026-08-08

`SHA256SUMS` for v2.1.0-rc7 was NOT produced by a full `mk-release.sh` run.
Only its last two steps were executed by hand, over the artifact set already
present in `~/rc7-artifacts/release-rc7/`.

## Why

The rc7 image was built on a cloud instance destroyed after artifact
retrieval. The local Yocto deploy tree holds build `20260721023917` (21 July),
while the released artifacts are from build `20260805102343`.

`mk-release.sh` guards only that all rootfs artifacts share ONE build
timestamp. The July build is internally consistent, so the guard passes. A
full run would therefore have silently overwritten the released image, SBOM,
manifest and testdata with July equivalents, and — because `~/vulns-master`
is present — re-run `enrich-cve.sh` against the July tree, replacing the
`cve-rock5a.enriched.json` regenerated on 7 August with the fixed script.

The script has no check that the deploy tree matches the tag being released.
Adding one (compare `ts_of` against `build_id` in the coverage manifest) is
an open task.

**Closed since.** `scripts/mk-release.sh` now reads `manifest.build_id` from
the coverage manifest and refuses to assemble when it does not match the
deploy tree, before writing anything. `ALLOW_BUILD_ID_MISMATCH=1` overrides
it and marks the output as not a valid release. The manifest is the only file
in the pipeline that is committed, pinned to the tag and covered by the
release signature, which is what makes it the thing to check against. The
rest of this report is the record of the 8 August run and is unchanged.

## What was executed

    cd ~/rc7-artifacts/release-rc7
    cp -L <repo>/security/coverage-rock5a.v2.1.0-rc7.yaml coverage-rock5a.v2.1.0-rc7.yaml
    shopt -s nullglob; files=( * ); shopt -u nullglob
    sha256sum -- "${files[@]}" | LC_ALL=C sort -k2 > SHA256SUMS

Identical in semantics to lines 187-196 of `scripts/mk-release.sh`.

## Result

11 files hashed. `SHA256SUMS` excluded from its own glob (array built before
the redirect). Released image hash unchanged before and after the operation:
`e188c0daad97b287fa65e881e7e76b4a5a8a9df7bfc60cb389f870e5c1d18014`.
