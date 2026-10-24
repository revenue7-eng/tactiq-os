# The SSH token plugin fetches a LUKS key from a remote SSH server. The
# device has no network role, so the plugin and its libssh dependency are
# left out of the image. veritysetup, integritysetup and LUKS are unaffected.
# The :tactiq override limits this to the TactiQ distro: a distro that
# reuses this layer keeps the upstream behaviour.
PACKAGECONFIG:remove:tactiq = "ssh-token"
