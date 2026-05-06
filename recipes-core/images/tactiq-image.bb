# TactiQ OS — PRODUCTION image profile
# ============================================================================
# Canonical image for tagged releases. Hardened posture:
#   - No debug-tweaks (root account is locked, no passwordless login)
#   - No OpenSSH server in the image
#   - No interactive debug tooling
#
# Built from the same component set as the development profile
# (`tactiq-image-dev.bb`) but with development-only IMAGE_FEATURES and
# packages explicitly removed.
#
# Build: MACHINE=tactiq-rock5a bitbake tactiq-image
# ============================================================================
SUMMARY = "TactiQ OS — production profile"

require tactiq-image-dev.bb

# ---------------------------------------------------------------------------
# Disable development conveniences
# ---------------------------------------------------------------------------
# Remove debug-tweaks (it is appended unconditionally in the dev recipe).
# Yocto resolves _append/_remove against the same scope, so the override
# below cancels the dev recipe's append for this build target.
EXTRA_IMAGE_FEATURES:remove = "debug-tweaks"

# Production root account is locked. The agent and its services run under
# their SELinux domains; there is no interactive root login path on a
# production image. Lock the account by setting an invalid password hash
# via the extrausers class.
INHERIT += "extrausers"
EXTRA_USERS_PARAMS = "usermod -p '!' root;"

# ---------------------------------------------------------------------------
# No SSH server in the production image
# ---------------------------------------------------------------------------
IMAGE_FEATURES:remove = "ssh-server-openssh"
IMAGE_INSTALL:remove = "openssh-sshd openssh-ssh openssh-keygen"

# ---------------------------------------------------------------------------
# No interactive debug tooling
# ---------------------------------------------------------------------------
# Reserved as the canonical place to remove tooling that may be appended
# in the dev recipe for bring-up convenience. Dev recipe currently has
# strace/tcpdump/nano/less commented out; if they get re-enabled there
# in future, listing them here keeps the production image clean by
# default.
IMAGE_INSTALL:remove = "strace tcpdump nano less"
