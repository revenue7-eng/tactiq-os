# Bundles reach the device on removable media, never over the network.
# network (HTTP download through libcurl) and streaming (HTTP streaming
# install) are upstream defaults and are left out of the image.
PACKAGECONFIG:remove = "network streaming"
