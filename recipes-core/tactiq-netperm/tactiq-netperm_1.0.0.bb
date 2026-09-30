SUMMARY = "Site network permission for tactiq-agent"
DESCRIPTION = "Oneshot unit that reads a signed permission file from \
/data/site, checks its signature against a dedicated permission key and its \
device line against the SoC serial number, and sets IPAddressAllow= on \
tactiq-agent at runtime. IPAddressDeny=any stays in the agent unit; a \
missing or rejected file leaves the agent without network. Design: \
THREAT_MODEL.md, agent network exception."
HOMEPAGE = "https://github.com/revenue7-eng/tactiq-os"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# The public half of the permission key. Development default is in pki/dev;
# a production build must point TACTIQ_NETPERM_PUBKEY outside the tree, and
# tactiq-keygate halts parsing if it does not.
SRC_URI = "file://tactiq-netperm \
           file://tactiq-netperm.service \
          "

UNPACKDIR = "${WORKDIR}/sources"
S = "${UNPACKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "tactiq-netperm.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install() {
    install -d ${D}${sbindir}
    install -m 0755 ${UNPACKDIR}/tactiq-netperm ${D}${sbindir}/tactiq-netperm
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/tactiq-netperm.service ${D}${systemd_system_unitdir}/tactiq-netperm.service
    install -d ${D}${datadir}/tactiq
    install -m 0644 ${TACTIQ_NETPERM_PUBKEY} ${D}${datadir}/tactiq/netperm.pem
}
do_install[file-checksums] += "${TACTIQ_NETPERM_PUBKEY}:True"

FILES:${PN} += "${datadir}/tactiq/netperm.pem"

# openssl verifies the signature; systemctl applies the property.
RDEPENDS:${PN} = "openssl-bin systemd"
