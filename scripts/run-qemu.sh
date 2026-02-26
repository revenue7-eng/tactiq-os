#!/bin/bash
# TactiQ OS QEMU launcher with persistent /data and swtpm
set -e

DEPLOY=~/tactiq-os/yocto/build/tmp-glibc/deploy/images/qemux86-64
KERNEL=${DEPLOY}/bzImage
ROOTFS=${DEPLOY}/tactiq-image-qemux86-64.rootfs.ext4
DATA_IMG=~/tactiq-os/data-persist.raw
TPM_DIR=/tmp/mytpm

# Create persistent data disk (once)
if [ ! -f "${DATA_IMG}" ]; then
    echo ">>> Creating persistent data disk..."
    RAW_TMP=$(mktemp /tmp/data-raw-XXXXXX.img)
    dd if=/dev/zero of="${RAW_TMP}" bs=1M count=512
    mkfs.ext4 -L data -q "${RAW_TMP}"
    qemu-img convert -f raw -O qcow2 "${RAW_TMP}" "${DATA_IMG}"
    rm -f "${RAW_TMP}"
    echo ">>> Data disk created: ${DATA_IMG}"
fi

# Start swtpm
rm -rf "${TPM_DIR}" && mkdir -p "${TPM_DIR}"
swtpm socket \
    --tpmstate dir="${TPM_DIR}" \
    --tpm2 \
    --ctrl type=unixio,path="${TPM_DIR}/swtpm-sock" \
    --flags not-need-init \
    --log level=0 \
    --daemon

echo ">>> Launching TactiQ OS..."
qemu-system-x86_64 \
    -cpu max \
    -m 512 \
    -kernel "${KERNEL}" \
    -drive file="${ROOTFS}",format=raw,if=virtio,readonly=on \
    -drive file="${DATA_IMG}",format=raw,if=virtio \
    -append "root=/dev/vda console=ttyS0 enforcing=1 systemd.gpt_auto=0 loglevel=1 audit=1" \
    -nographic \
    -chardev socket,id=chrtpm,path="${TPM_DIR}/swtpm-sock" \
    -tpmdev emulator,id=tpm0,chardev=chrtpm \
    -device tpm-tis,tpmdev=tpm0 \
    -netdev user,id=net0 \
    -device virtio-net-pci,netdev=net0 \
    -smbios type=1,serial=TACTIQ-QEMU-001,uuid=12345678-1234-1234-1234-123456789abc
