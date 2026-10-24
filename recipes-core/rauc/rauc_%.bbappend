# Bundles reach the device on removable media, never over the network.
# network (HTTP download through libcurl) and streaming (HTTP streaming
# install) are upstream defaults and are left out of the image.
# The :tactiq override limits this to the TactiQ distro: a distro that
# reuses this layer keeps the upstream behaviour.
PACKAGECONFIG:remove:tactiq = "network streaming"
