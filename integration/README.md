# meta-rauc wrynose carry patch

Local TactiQ fixes to meta-rauc for Yocto wrynose compatibility,
exported from local branch tactiq/wrynose-fixes.

Upstream:    https://github.com/rauc/meta-rauc.git
Base commit: fa18cf1 (origin/scarthgap, rauc v1.15.2)
Patch:       meta-rauc-wrynose.patch  (git format-patch, 1 commit)

Changes:
  - conf/layer.conf       : allow LAYERSERIES_COMPAT wrynose
  - recipes-core/rauc/*   : install file:// payloads from UNPACKDIR

Apply from a clean meta-rauc checkout at the base commit:
  git am < meta-rauc-wrynose.patch

Status: interim carry to prevent loss. Proper resolution (pinned
tarball snapshot + patch, consistent with the other layers) is
tracked together with LAYERS.lock.
