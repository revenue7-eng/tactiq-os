# scripts/mk-release.sh checks the re-signed bundle with
# `rauc info --output-format=json`. meta-rauc enables json for the target
# rauc only (rauc-target.inc); the native rauc that runs on the build host
# needs it as well, or the release check cannot run.
PACKAGECONFIG:append = " json"
