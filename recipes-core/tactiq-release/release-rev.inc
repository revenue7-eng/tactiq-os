# Release identity recorded in /etc/tactiq-release by
# classes-recipe/tactiq-release-identity.bbclass.
#
# Both values live in the repository so that they travel with the tag: anyone
# who clones a release tag and builds it produces the same image identity we
# publish, without setting anything. They are set by whoever cuts the release,
# in the commit that is tagged. scripts/mk-release.sh reads /etc/tactiq-release
# back from the release image and refuses to assemble a release whose image
# does not name the tag being released, so a missed update stops the release
# instead of shipping (v2.1.0-rc11 shipped naming v2.1.0-rc9).
#
# Between releases these hold the tag the working tree descends from and its
# release date, which is what a development build should report.

TACTIQ_OS_RELEASE_REV = "v2.1.0-rc12"
TACTIQ_OS_RELEASE_DATE = "2026-09-24"
