# LLM inference latency on Rock 5A, 2026-10-29

## Summary

Prompt-read and token-generation throughput for two quantized models on Radxa
Rock 5A (RK3588S), CPU only, measured with `llama-bench` under five thread and
affinity configurations.

**Headline:** on this SoC generation throughput saturates per CPU cluster, not
per core and not at the DRAM limit. Two A76 cores already reach 9.33 tok/s and
four reach 10.27, while loading the second cluster concurrently raises the total
to 16.52 tok/s. Prompt reading is compute-bound and is made slower, not faster,
by including the A55 cores.

Raw output: `logs/llm-latency-20261029-board.log` (cold boot and the whole
console session, as produced).

## Environment

| Item | Value |
|---|---|
| Board | Radxa ROCK 5A (RK3588S), 4x Cortex-A76 + 4x Cortex-A55 |
| RAM | 4 GiB LPDDR4X, 2112 MHz, 4 channels x 1024 MB |
| OS | TactiQ OS v2.1.0-rc14 (tactiq-image-dev), slot A |
| Kernel | 6.18.52-yocto-standard-00164-g0e7b072c8239 |
| Root | dm-verity, dm-0 "rootfs" |
| SELinux | enforcing |
| IMA | policy: measure 8, appraise 4 |
| cpufreq | schedutil; max 1.80 GHz (cpu0-3), 2.40 GHz (cpu4-5, cpu6-7) |
| cpuidle | governor menu; states WFI, cpu-sleep |
| Benchmark tool | `llama-bench` 0.5.0-dev, build 11396, commit `2e7c58c54` |
| Tool build | cross-compiled aarch64, GNU 13.3.0, `-static-libstdc++ -static-libgcc`, `GGML_OPENMP=OFF`, `GGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16` |
| tactiq-os tree at run time | main @ 4a805d7 |

The booted image predates that tree revision; it is recorded as context. The
subject of this report is the runtime and the weights, not the tree.

## Model provenance

| Field | Value |
|---|---|
| Source | `openbmb/MiniCPM5-2B-GGUF` @ `2079a22f3beaa4e306449978533478fe0522f4b3` |
| File | MiniCPM5-2B-Q4_K_M.gguf |
| Size | 1561318368 bytes |
| SHA256 | `ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd` |
| Verified on board | `sha256sum -c` after transfer: OK |
| GGUF metadata | `general.architecture = llama`, `tokenizer.ggml.model = gpt2`, `tokenizer.ggml.pre = minicpm5` |
| Reported by runtime | 2.52 B parameters, 1.45 GiB |
| Licence | Apache-2.0 |

Comparison model, already on the test medium from the 2026-10-09 run:
`qwen2.5-3b-instruct-q4_k_m.gguf`, 2104932768 bytes, reported by the runtime as
3.40 B parameters and 1.95 GiB.

`tokenizer.ggml.pre = minicpm5` is handled in commit `2e7c58c54`
(`LLAMA_VOCAB_PRE_TYPE_MINICPM5`, `ignore_merges = true`). An unhandled value
there is a `throw`, not a warning, so this was a load-or-fail property of the
pairing and not a quality caveat.

## Method

`llama-bench` with `-p 512 -n 128` (prompt and generation) or `-p 0 -n 128`
(generation only), `-r` set per row, `--cpu-mask` with `--cpu-strict 1` for
affinity. Mask `0xF0` is cpu4-7 (A76), `0x0F` is cpu0-3 (A55), `0x30` is
cpu4-5.

Weights were read by `mmap` from a read-only vfat USB medium; the binary was
copied to `/tmp` (tmpfs) and executed from there. The two concurrent instances
used the same weights file, so one copy was shared in the page cache and the
measurement is not confounded by memory pressure.

## Results

| # | model | config | pp512 tok/s | tg128 tok/s | reps |
|---|---|---|---|---|---|
| 1 | MiniCPM5-2B | 4 threads, 0xF0 | 34.51 +/- 0.06 | 10.27 +/- 0.02 | 3 |
| 2 | Qwen2.5-3B | 4 threads, 0xF0 | 23.97 +/- 0.19 | 7.57 +/- 0.02 | 3 |
| 3 | MiniCPM5-2B | 8 threads, no mask | 30.71 +/- 1.03 | 11.52 +/- 0.31 | 3 |
| 4 | MiniCPM5-2B | 4 threads, 0x0F | 8.36 +/- 0.00 | 4.13 +/- 0.00 | 2 |
| 5 | MiniCPM5-2B | 2 threads, 0x30 | not run | 9.33 +/- 0.01 | 4 |

Two instances of the same weights file, concurrently, generation only:

| config | tg128 tok/s | reps |
|---|---|---|
| 4 threads, 0xF0 | 12.89 +/- 0.25 | 5 |
| 4 threads, 0x0F | 3.63 +/- 0.14 | 2 |
| total | 16.52 | |

The same `-p 0 -n 128 -t 4 --cpu-mask 0xF0 -r 5` command run alone, as the
control for the 12.89 figure, gives 10.27 +/- 0.03 and 10.26 +/- 0.02 on two
separate runs. The rise under concurrent load is therefore not an artefact of
the command form.

## What the numbers say

Multiplying `tg128` by the on-disk weight size gives the rate at which weights
are read: 14.9 GiB/s for row 1 and 14.8 GiB/s for row 2. Two different models
converging on one figure is the signature of a generation phase limited by
reading weights rather than by arithmetic.

That limit is per cluster. Row 5 against row 1: doubling from two A76 cores to
four adds 10 percent (9.33 to 10.27 tok/s, 13.5 to 14.9 GiB/s). The second and
third core pair contribute almost nothing, so the constraint is not the number
of cores. Nor is it the DRAM: two instances on separate clusters reach 16.52
tok/s in total, which is 24.0 GiB/s.

Prompt reading behaves the opposite way. Row 3 against row 1: adding the four
A55 cores lowers `pp512` from 34.51 to 30.71 tok/s and raises the standard
deviation from 0.06 to 1.03. Work is divided evenly across threads, so the A76
cores wait on the A55 cores. For prompt reading, exactly four A76 cores with
strict affinity is the fastest configuration available on this board.

At equal quantization the smaller model is faster in both phases: rows 1 and 2
differ by a factor of 1.44 on `pp512` and 1.36 on `tg128` in favour of the 2.52 B
model.

## Unexplained: the A76 instance speeds up under load

The A76 instance generates faster with the A55 cluster busy (12.89 tok/s) than
alone (10.27). Three candidate causes were each excluded by measurement:

| candidate | check | result |
|---|---|---|
| CPU frequency scaling | `scaling_cur_freq` sampled 10 s into a solo A76 run | cpu4-7 already at 2.40 GHz, their maximum |
| DDR frequency scaling under Linux | `/sys/class/devfreq/` | no devfreq device present |
| deep CPU idle state exit cost | `cpuidle/state1/disable` set to 1 on cpu4-7, solo run repeated | 10.26 tok/s, unchanged; restored to 0 afterwards |

Two causes remain and are not distinguished by anything observable from the OS.
The DRAM controller may use more of its capacity when more independent requests
are in flight. Or the memory frequency may be raised by firmware: the boot log
shows BL31 declaring four DDR operating points (2112, 528, 1068, 1560 MHz) while
Linux has no interface to them, so such a change would be invisible to the OS.
This report does not choose between the two.

## Scope limits

Thermal governors are registered in the kernel, but no thermal zone device
appears in the boot log and no temperature was read. Behaviour under sustained
load is not covered.

Neither the weights path (vfat) nor the binary path (tmpfs) is subject to IMA
appraisal. This is a measurement configuration, not a delivery configuration;
the signed-delivery path for model weights is a separate open item.

`llama-bench` sizes the context to the test, 512 prompt tokens plus 128
generated. These figures say nothing about long context. The model declares a
native context of 131072 tokens; at 42 layers and 2 KV heads the KV cache for
the full context exceeds the RAM on this board.

The published benchmark scores for the model are its publisher's and were not
reproduced here. Only throughput was measured.

The raw log contains shell tab-completion dumps and mistyped command lines. The
serial console runs without hardware flow control, so a pasted line can lose its
leading characters; the retries are in the log as produced.

## When this stops holding

Run again after any of these, not on a date:

- the `llama-bench` binary is rebuilt from a different llama.cpp revision
- the weights file changes (a different SHA256 in the table above)
- the image changes the cpufreq governor, the cpuidle states, or the DDR
  operating points set by the bootloader
- the measurement moves to another board (Rock 5T, Raspberry Pi 4) or another
  memory configuration
- the weights are served from a medium that cannot be mapped, which would add
  read cost this measurement does not contain
