# Crate list for tactiq-agent, taken from the Cargo.lock committed at the
# SRCREV this recipe pins. Regenerate with 'bitbake -c update_crates
# tactiq-agent' after moving SRCREV; the two must not be edited apart.
#
# Eleven crates, all pure computation reached through sha2 and hex. The
# agent depends on attest-envelope alone, which is why this list is short
# enough to read: no async runtime, no TLS stack, no serialisation
# framework inside the TCB.

SRC_URI += " \
    crate://crates.io/block-buffer/0.10.4 \
    crate://crates.io/cfg-if/1.0.4 \
    crate://crates.io/cpufeatures/0.2.17 \
    crate://crates.io/crypto-common/0.1.7 \
    crate://crates.io/digest/0.10.7 \
    crate://crates.io/generic-array/0.14.7 \
    crate://crates.io/hex/0.4.3 \
    crate://crates.io/libc/0.2.189 \
    crate://crates.io/sha2/0.10.9 \
    crate://crates.io/typenum/1.20.1 \
    crate://crates.io/version_check/0.9.5 \
"

SRC_URI[block-buffer-0.10.4.sha256sum] = "3078c7629b62d3f0439517fa394996acacc5cbc91c5a20d8c658e77abd503a71"
SRC_URI[cfg-if-1.0.4.sha256sum] = "9330f8b2ff13f34540b44e946ef35111825727b38d33286ef986142615121801"
SRC_URI[cpufeatures-0.2.17.sha256sum] = "59ed5838eebb26a2bb2e58f6d5b5316989ae9d08bab10e0e6d103e656d1b0280"
SRC_URI[crypto-common-0.1.7.sha256sum] = "78c8292055d1c1df0cce5d180393dc8cce0abec0a7102adb6c7b1eef6016d60a"
SRC_URI[digest-0.10.7.sha256sum] = "9ed9a281f7bc9b7576e61468ba615a66a5c8cfdff42420a70aa82701a3b1e292"
SRC_URI[generic-array-0.14.7.sha256sum] = "85649ca51fd72272d7821adaf274ad91c288277713d9c18820d8499a7ff69e9a"
SRC_URI[hex-0.4.3.sha256sum] = "7f24254aa9a54b5c858eaee2f5bccdb46aaf0e486a595ed5fd8f86ba55232a70"
SRC_URI[libc-0.2.189.sha256sum] = "3eaf3ede3fee6db1a4c2ee091bf8a8b4dccdc6d17f656fb07896ee72867612f2"
SRC_URI[sha2-0.10.9.sha256sum] = "a7507d819769d01a365ab707794a4084392c824f54a7a6a7862f8c3d0892b283"
SRC_URI[typenum-1.20.1.sha256sum] = "b6f5e870be6c3b371b77fe0ee0bafb859fa4964b4404c27de1d380043c4dda20"
SRC_URI[version_check-0.9.5.sha256sum] = "0b928f33d975fc6ad9f86c8f283853ad26bdd5b10b7f1542aa2fa15e2289105a"
