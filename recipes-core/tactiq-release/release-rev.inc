# Release revision recorded in /etc/tactiq-release.
#
# This lives in the repository so that it travels with the tag: anyone who
# clones a release tag and builds it produces the same image identity we
# publish, without setting anything. It is set by whoever cuts the release,
# immediately before the tag is created.
#
# Between releases this holds the tag the working tree descends from, which
# is what a development build should report.

TACTIQ_OS_RELEASE_REV = "v2.1.0-rc7"
