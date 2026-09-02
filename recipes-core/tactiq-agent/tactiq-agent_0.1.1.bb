SUMMARY = "TactiQ attestation agent"
DESCRIPTION = "Produces the canonical attestation envelope from the platform TPM: \
device_id(16) || counter_be(8) || pcr_selection(5) || pcr_hash(32) || \
evidence_hash(32), signed with an ECDSA P-256 key held inside the TPM. The \
evidence hash binds an accompanying bundle to the signature; an edge node has \
no sub-attesters, so the agent attests an empty bundle and that absence is \
signed like everything else. Freshness comes from a TPM NV monotonic \
counter, so a device can attest after months offline with no server nonce, no \
CA and no NTP."
HOMEPAGE = "https://github.com/revenue7-eng/tactiq-attest"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=3b83ef96387f14655fc854ddc3c6bd57"

# The device side of attestation lives in its own repository. The verifier —
# signature checking, the anti-replay high-water mark, the durable write and
# the reference-value appraisal — is a separate closed component and is not
# built here. The Custinel workspace pins this same revision, so the two sides
# of the protocol are the same code, not two implementations kept in step by
# review.
#
# That claim is checkable, and it silently stopped being true once: this
# recipe stayed on 84362d39 while Custinel moved to 8d77e2ac, and the
# paragraph above went on asserting they matched. Verify with
#   grep tactiq-attest Cargo.lock
# in the Custinel workspace; the rev there must equal SRCREV below.
SRCREV = "8d77e2acbe69cf0e8e73292a6bc4c90c223584ac"
SRC_URI = "git://github.com/revenue7-eng/tactiq-attest.git;protocol=https;branch=main"
SRC_URI += "file://tactiq-agent.service"


# Eleven crates, all pure computation reached through sha2 and hex. The agent
# depends on attest-envelope alone: no async runtime, no TLS stack and no
# serialisation framework inside the TCB. The list below is generated, so this
# note lives here rather than in it.
require tactiq-agent-crates.inc

inherit cargo cargo-update-recipe-crates systemd useradd

# Only the agent binary. The workspace also holds attest-envelope, which is a
# library and has nothing to install.
CARGO_BUILD_FLAGS += " --bin tactiq-agent"

# Reproducibility: strip the build path out of the binary and let cargo see the
# release timestamp. Same treatment as agentgateway in this layer.
RUSTFLAGS += "--remap-path-prefix=${WORKDIR}=/usr/src/debug/${PN}/${PV}"
export SOURCE_DATE_EPOCH

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
# The agent reaches the TPM through tpm2-tools. That is the current state of
# crates/prover/src/tpm.rs and it is deliberate: the command sequence matches
# the harness that validated the protocol against the verifier, and it behaves
# identically against swtpm and a discrete chip.
#
# It is also why tpm2-tools is an RDEPENDS rather than just the libtss2
# runtime. When that module is ported to tss-esapi, this line becomes
# "libtss2 libtss2-mu libtss2-tcti-device" and the tools drop out of the
# production image.
RDEPENDS:${PN} = "tpm2-tools libtss2 libtss2-mu libtss2-tcti-device"

# ---------------------------------------------------------------------------
# User and device access
# ---------------------------------------------------------------------------
# tpm2-tss ships udev rules giving /dev/tpm[rm]0 to group tss. Without the
# supplementary group the DeviceAllow= in the unit would grant a node the
# process still could not open. USERADD_DEPENDS makes the group exist before
# this recipe's useradd runs.
USERADD_PACKAGES = "${PN}"
USERADD_PARAM:${PN} = "--system --no-create-home --shell /sbin/nologin \
                       --home-dir /var/lib/tactiq-agent -g tactiq-agent --groups tss \
                       tactiq-agent"
GROUPADD_PARAM:${PN} = "--system tactiq-agent"
USERADD_DEPENDS = "tpm2-tss"

SYSTEMD_SERVICE:${PN} = "tactiq-agent.service"
SYSTEMD_AUTO_ENABLE = "disable"

do_install:append() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${B}/target/${CARGO_TARGET_SUBDIR}/tactiq-agent ${D}/opt/tactiq/bin/tactiq-agent

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/tactiq-agent.service ${D}${systemd_system_unitdir}/

    # Identity and key live on the persistent partition, not in the image: the
    # same image is flashed to every unit, so anything carried here would be
    # identical fleet-wide and could not serve as an identity.
    #
    # keys/ is 0700 because it holds the device id and the public key, which
    # are provisioned as one pair and must live and die together — a device id
    # surviving a regenerated key would reach the verifier looking exactly like
    # a forgery.
    install -d -m 0700 -o tactiq-agent -g tactiq-agent ${D}/data/tactiq/keys
    install -d -m 0750 -o tactiq-agent -g tactiq-agent ${D}/data/tactiq/audit
    install -d -m 0755 -o tactiq-agent -g tactiq-agent ${D}/data/tactiq/certs
    install -d -m 0700 -o tactiq-agent -g tactiq-agent ${D}/data/tactiq/counter

    # cargo installs to ${bindir}; the agent belongs under /opt/tactiq with the
    # rest of the TactiQ binaries.
    rm -rf ${D}${bindir}
}

FILES:${PN} = " \
    /opt/tactiq/bin/tactiq-agent \
    ${systemd_system_unitdir}/tactiq-agent.service \
    /data/tactiq \
"
