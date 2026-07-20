# NPU Latency Measurement — Rock 5A — 2026-06-25

## Summary

Quantized MobileNet v1 inference latency on Radxa Rock 5A (RK3588S), TactiQ OS
hardened-edge, kernel 6.18.24-yocto-standard. Model baked into the rootfs from
the recipe (no manual staging). NPU offload via Mesa Teflon external delegate.

**Headline:** 13.78 ms per inference via Teflon delegate, sustained without
thermal throttling over 2000 runs.

## Environment

| Item | Value |
|---|---|
| Board | Radxa Rock 5A (RK3588S) |
| OS | TactiQ OS hardened-edge, SELinux enforcing |
| Kernel | 6.18.24-yocto-standard-00130-g3f14dbbb6e70 |
| Image | tactiq-image-npu, wic 20260625120534 |
| Accelerator node | /dev/accel/accel0 (rocket driver) |
| Delegate | /usr/lib/libteflon.so (Mesa Teflon, 2627984 bytes) |
| Benchmark tool | benchmark_model (TFLite 2.21.0, upstream) |

## Model provenance

| Field | Value |
|---|---|
| File | mobilenet_v1_1.0_224_quant.tflite |
| Size | 4276352 bytes |
| SHA256 | ecc3a67c47c5a609ec35f6a58a7d97532834e43df4cb7d3f1204a8164b7d20dd |
| Source tarball | mobilenet_v1_2018_08_02 (quant release) |
| Tarball SHA256 | d32432d28673a936b2d6281ab0600c71cf7226dfe4cdcef3012555f691744166 |
| SELinux context | system_u:object_r:usr_t:s0 (standard rootfs labeling) |

Note: the float reference model ships from the mobilenet_v1_2018_02_22 release;
the quantized model from mobilenet_v1_2018_08_02. Two distinct mobilenet
releases — stated explicitly to avoid reproducer confusion over the two dates.

## Method

benchmark_model run against the quantized model under three configurations.
Speedup is baseline-dependent and is reported against both baselines rather
than as a single figure.

Delegate coverage: the external delegate executes the graph **partially**
(2 delegate kernels), with the remainder on the XNNPACK CPU delegate. This is
a property of Teflon operator coverage for mobilenet_v1, not a fault. The
reported delegate latency therefore reflects partial NPU offload.

Commands:

    # Naive CPU baseline (1 thread, no XNNPACK)
    ./benchmark_model --graph=mobilenet_v1_1.0_224_quant.tflite \
      --num_threads=1 --use_xnnpack=false --num_runs=50 --warmup_runs=5

    # Optimized CPU baseline (4 threads, XNNPACK)
    ./benchmark_model --graph=mobilenet_v1_1.0_224_quant.tflite \
      --num_threads=4 --num_runs=50 --warmup_runs=5

    # Teflon delegate
    ./benchmark_model --graph=mobilenet_v1_1.0_224_quant.tflite \
      --external_delegate_path=/usr/lib/libteflon.so \
      --num_runs=50 --warmup_runs=5

## Results

| Configuration | Inference avg | std | Notes |
|---|---|---|---|
| Naive CPU (1 thread, no XNNPACK) | 54.17 ms | 63 us | reference ceiling |
| Optimized CPU (4 threads, XNNPACK) | 17.86 ms | 92 us | strict CPU baseline |
| Teflon delegate (50 runs) | 13.78 ms | 84 us | partial NPU offload |
| Sustained (2000 runs, 180 s cap) | 13.81 ms | 155 us | no throttling |
| Multi-run (3 x 50 runs) | 13.81 / 13.84 / 13.93 ms | — | run-to-run spread 0.9% |

### Speedup

| Baseline | Speedup |
|---|---|
| vs naive CPU (54.17 ms) | 3.93x |
| vs optimized CPU (17.86 ms) | 1.30x |

The 1.30x figure against the optimized XNNPACK CPU baseline is the
conservative, defensible number. The 3.93x figure against the naive baseline
is also valid; the difference is entirely the choice of baseline.

## Thermal under load

Background per-second log across the full measurement session (287 samples).
Idle start 29.6 C across all zones.

| Zone | Idle | Peak | Delta |
|---|---|---|---|
| npu-thermal (zone6) | 29.6 C | 33.3 C | +3.7 C |
| bigcore0-thermal (zone1) | 29.6 C | 37.9 C | +8.3 C |
| bigcore2-thermal (zone2) | 29.6 C | 37.9 C | +8.3 C |

The big CPU cores heat more than the NPU because the XNNPACK fallback portion
of the graph runs on CPU while the NPU handles 2 kernels. All zones remain far
below the throttle threshold, consistent with the flat sustained latency.

## Raw logs

In measurements/logs/: cpu-baseline.log, cpu-baseline-1thread.log,
npu-delegate.log, npu-sustained.log, npu-multirun.log, thermal-npu.log
(287 lines). Captured on-device, retrieved via card reader.

Note on timestamps: the board has no battery-backed RTC and no NTP, so its
clock starts from a fixed build epoch. File mtimes and dmesg dates inside the
logs do not reflect wall-clock time and are not provenance. Session dating is
2026-06-25 per the host-built image timestamp (wic 20260625120534). Model
provenance is by SHA256, not by file date.

## Reproduction

1. Flash tactiq-image-npu (wic 20260625120534) to Rock 5A.
2. Confirm /dev/accel/accel0 and /usr/lib/libteflon.so present.
3. Run the three commands above from
   /usr/share/tensorflow/lite/tools/benchmark/.
