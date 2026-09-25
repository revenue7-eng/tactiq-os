SUMMARY = "TactiQ attestation agent"
DESCRIPTION = "Produces the canonical attestation envelope from the platform TPM: \
device_id(16) || counter_be(8) || pcr_selection(5) || pcr_hash(32) || \
evidence_hash(32). Each cycle the TPM quotes the selected PCRs with a \
restricted ECDSA P-256 attestation key held inside it, the quote committing \
to the envelope; a verifier checks that the TPM's own PCR digest matches. The \
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
# Compatibility is defined by the attest-envelope crate VERSION (currently
# 0.2.0, envelope v2: TPM2_Quote under a restricted AK, tactiq-attest
# DDR-004), not by this git rev. The prover's rev moves on changes to the agent
# (main.rs, tpm.rs, state.rs) that do not touch the wire format, so SRCREV here
# and the attest-envelope rev pinned in Custinel's Cargo.lock need NOT match
# commit-for-commit. They must agree only when the envelope format changes,
# which bumps attest-envelope's version. Verify the crate version on both
# sides, not the rev:
#   grep -A1 'name = "attest-envelope"' Cargo.lock   # in the Custinel workspace
# History note: these revs previously drifted (recipe on 84362d3, Custinel on
# 8d77e2ac) and a "must match" comment masked it. Version-parity is the real
# invariant; a rev mismatch under one envelope version is expected.
SRCREV = "f437e3a01e7c387328b3b7d9f2e8fcdd5f73dcea"
SRC_URI = "git://github.com/revenue7-eng/tactiq-attest.git;protocol=https;branch=main"
SRC_URI += "file://tactiq-agent.service"


# The agent depends on attest-envelope alone, reaching sha2 and hex: no async
# runtime, no TLS stack and no serialisation framework inside the TCB. The
# crate list below is longer than that (45 crates) because cargo resolves the
# whole tactiq-attest workspace, which also holds the verifier library
# attest-appraise (p256, serde_json). Without them the offline build fails at
# resolution. They are fetched, not compiled into the agent: see `-p prover`
# below. The list is generated, so this note lives here rather than in it.
require tactiq-agent-crates.inc

inherit cargo cargo-update-recipe-crates systemd useradd

# Only the agent binary. The workspace also holds attest-envelope, which is a
# library and has nothing to install.
#
# `-p prover` is load-bearing. With `--bin` alone cargo unifies features across
# every workspace member, so p256 in attest-appraise turns on extra digest
# features and const-oid, subtle and zeroize get compiled into the agent. With
# `-p prover` only the envelope's dependency tree is built.
CARGO_BUILD_FLAGS += " -p prover --bin tactiq-agent"

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
