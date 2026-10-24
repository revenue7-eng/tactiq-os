#!/usr/bin/env bash
#
# check-attribution.sh: refuse AI-assistant attribution in commit metadata.
#
# Commits and pull requests in this repository carry no assistant
# attribution: no Co-authored-by trailer naming an assistant, no session
# link, no "Generated with" line. Assistant tools add such lines by default,
# so the rule is enforced by this check, not by anyone's memory.
#
#   check-attribution.sh --file <path>    a commit message (commit-msg hook)
#   check-attribution.sh --range <a>..<b> every commit message in a range (CI)
#   check-attribution.sh --stdin          text on stdin (a pull request body)
#
# Exit 0 when clean, 1 when a line matches (the lines are printed).
#
# Seven commits merged before this check (fe47510 to fd1e31d) carry such
# lines and stay: rewriting main would break the v2.1.0-rc14 tag, its signed
# RIM and its Rekor entry. CI therefore checks the commits of a pull
# request, never the whole history.
#
set -euo pipefail

PATTERN='co-authored-by:.*(claude|anthropic)|noreply@anthropic\.com|claude-session:|claude\.ai/code/session_|generated with \[?claude'

usage() { echo "usage: $0 --file <path> | --range <a>..<b> | --stdin" >&2; exit 2; }

text() {
  case "${1:-}" in
    --file)  [ -n "${2:-}" ] || usage; cat -- "$2" ;;
    --range) [ -n "${2:-}" ] || usage; git log --format='%H%n%B' "$2" ;;
    --stdin) cat ;;
    *) usage ;;
  esac
}

if hits="$(text "$@" | grep -inE "$PATTERN")"; then
  echo "assistant attribution found; remove these lines:" >&2
  echo "$hits" >&2
  exit 1
fi
exit 0
