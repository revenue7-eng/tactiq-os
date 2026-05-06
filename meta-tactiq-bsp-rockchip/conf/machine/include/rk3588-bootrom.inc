# RK3588 BootROM contract.
# idbloader.img -> sector 64    (32 KiB)
# u-boot.itb    -> sector 16384 (8 MiB)
# Wic --offset takes KiB. Sector = KiB * 2.

RK3588_IDBLOADER_OFFSET_KIB := "32"
RK3588_UBOOT_OFFSET_KIB := "8192"
