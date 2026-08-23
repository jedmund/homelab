# `max` Hardware Upgrade Evaluation

Evaluated 2026-08-22 after expanding the GitLab Runner pool on `max`.

## Recommendation

The Ryzen Threadripper PRO 9975WX is the higher-value individual upgrade for
this host. It materially increases aggregate CI throughput and gives the AI
services more CPU isolation, while preserving the current platform, 350 W TDP,
and peak boost clock.

Moving from 128 GB to 256 GB is not required by the current ten-job runner
configuration. It is still a useful upgrade because the installed four-DIMM
layout populates only four of WRX90's eight memory channels. A matched
eight-DIMM kit would increase memory bandwidth as well as capacity, helping CPU
inference, compilation, model loading, and the filesystem cache.

The combined CPU and memory upgrade is the balanced choice if the target is
roughly 16 concurrent CI jobs while GPU inference remains online. Otherwise,
upgrade the CPU first and make the memory purchase only after measuring the new
runner pool under sustained load.

## Current system

These values were read from the live host rather than inferred from inventory.

| Component | Current state |
|---|---|
| CPU | AMD Ryzen Threadripper PRO 9955WX, 16 cores / 32 threads |
| Motherboard | ASRock WRX90 WS EVO |
| BIOS | 12.09, released 2026-02-04 |
| Memory | 128 GB: 4 x 32 GB ECC RDIMM at 5600 MT/s |
| Populated channels | A, C, E, and G; B, D, F, and H are empty |
| NUMA exposure | One Linux NUMA node |
| GPUs | 3 x RTX PRO 6000 Blackwell, 288 GB aggregate VRAM |
| Runner allocation | 10 jobs, capped at 3 logical CPUs and 6 GB per job |
| Runner worst-case budget | 30 logical CPUs and 60 GB of build-container RAM |
| Observed host memory | 125 GiB total, about 36 GiB used and 88 GiB available |

The live AI stack included DeepSeek V4 Flash on the two Max-Q GPUs and
llama-swap on the full-power GPU. The DeepSeek container used about 9.6 GiB of
host memory; llama-swap and its child servers used about 44 GiB including
mapped model data. The host was not under meaningful RAM pressure.

## CPU upgrade: 9955WX to 9975WX

AMD publishes the following specifications for the two processors:

| Specification | 9955WX | 9975WX | Change |
|---|---:|---:|---:|
| Cores / threads | 16 / 32 | 32 / 64 | 2x |
| Maximum boost | 5.4 GHz | 5.4 GHz | None |
| Base clock | 4.5 GHz | 4.0 GHz | -11% |
| L3 cache | 64 MB | 128 MB | 2x |
| Default TDP | 350 W | 350 W | None |
| Memory channels | 8 | 8 | None |
| Launch SEP | $1,649 | $4,099 | +$2,450 before resale |

Sources:

- [AMD Threadripper PRO 9000 WX launch specifications and pricing](https://www.amd.com/en/blogs/2025/amd-introduces-new-zen-5-based-ryzen-threadripper-pro.html)
- [AMD Ryzen Threadripper PRO 9975WX specifications](https://www.amd.com/en/products/processors/workstations/ryzen-threadripper/9000-wx-series/amd-ryzen-threadripper-pro-9975wx.html)
- [ASRock WRX90 WS EVO specifications](https://www.asrock.com/mb/AMD/WRX90%20WS%20EVO/index.us.asp)

### GitLab Runner impact

This is a significant aggregate-throughput upgrade, not a promise that one CI
job will complete twice as fast. A single job retains similar peak single-core
performance because both CPUs boost to 5.4 GHz, and the 9975WX has a lower base
clock. Multiple independent test, build, and browser jobs can use the doubled
core count directly.

The current 9955WX runner configuration can consume 30 of 32 logical CPUs at
its ten-job maximum. On the 9975WX, a conservative next configuration would be:

```yaml
gitlab_runner_linux_concurrent: 16
gitlab_runner_linux_cpus: "3"
gitlab_runner_linux_memory: 6g
```

That allocates at most 48 of 64 logical CPUs to CI and leaves 16 for
tokenization, inference orchestration, storage, and host services. Raise the
limit only after checking real queue depth and CPU saturation; additional
runner slots do not improve throughput when pipelines are not waiting.

### AI inference impact

The current large-model paths are primarily GPU- and VRAM-bound:

- DeepSeek V4 Flash holds approximately 167 GB across two 96 GB GPUs.
- The active llama.cpp model is GPU-offloaded to the third 96 GB GPU.
- The persistent CPU-only Qwen 4B model uses 12 threads and already fits within
  the 9955WX's 16 physical cores when CI is quiet.

Consequently, the 9975WX should not be expected to double single-request GPU
token generation. Its benefit is higher request-preparation and tokenization
capacity, better performance for concurrent CPU work, and much less contention
when CI and inference are busy together. CPU-only inference can scale when it
uses more than the current 12 threads or when multiple CPU workloads overlap.

### Platform compatibility

The WRX90 WS EVO officially supports Threadripper PRO 9000 WX processors and
the sTR5 socket. The current CPU and the 9975WX both have a 350 W default TDP,
so the upgrade does not inherently require a different motherboard, PSU, or
cooling class. The installed BIOS postdates the 9975WX launch, but its CPU
support should still be confirmed against ASRock's current support list before
the physical swap.

## Memory upgrade: 128 GB to 256 GB

### Capacity

Capacity alone is not a current bottleneck. With the AI services running, the
host had about 88 GiB available. Ten build containers can claim at most 60 GB,
leaving practical headroom at the current concurrency even before accounting
for the fact that most observed CI containers used less than their cap.

Additional capacity becomes important if any of these are planned:

- 16 or more concurrent 6 GB CI jobs;
- CPU offload for models that exceed available VRAM;
- more simultaneously resident CPU models or inference services;
- keeping the roughly 167 GB DeepSeek checkpoint hot in the filesystem cache
  to reduce repeated cold-load time.

More RAM alone will not materially increase steady-state tokens per second for
models whose weights and compute remain on the GPUs.

### Memory bandwidth

The current modules occupy channels A, C, E, and G. Installing a matched
eight-DIMM set would engage all eight memory channels. Approximate theoretical
bandwidth is:

| Layout | Approximate theoretical bandwidth |
|---|---:|
| Current 4 channels at 5600 MT/s | 179.2 GB/s |
| 8 channels at 4800 MT/s | 307.2 GB/s |
| 8 channels at 5600 MT/s | 358.4 GB/s |
| 8 channels at 6400 MT/s | 409.6 GB/s |

These are bus-width calculations, not measured application throughput. The
extra channels are most useful to CPU inference and fully parallel CPU jobs;
they have little effect on GPU-resident decode once model loading is complete.

### Use one matched eight-DIMM kit

SMBIOS reports a G.Skill part prefix matching the 128 GB
`F5-6400R3239G32GQ4-G5` kit. It is a 4 x 32 GB Intel XMP kit whose default SPD
speed is 5600 MT/s. G.Skill recommends it for Intel W790 and explicitly warns
against combining separately matched memory kits, even when the part numbers
match.

- [Current G.Skill 4 x 32 GB kit specifications](https://www.gskill.com/specification/400/443/1747204527/F5-6400R3239G32GQ4-G5-Specification)

Do not assume that adding another four-module kit will be stable. Prefer one
matched 8 x 32 GB kit listed for AMD WRX90. One candidate is the G.Skill G5 Neo
`F5-6400R3239G32GE8-G5N`, an octa-channel ECC RDIMM kit designed for WRX90.
Its default SPD speed is 4800 MT/s; 6400 MT/s requires enabling its AMD EXPO
profile and is subject to CPU and motherboard stability.

- [G.Skill G5 Neo 8 x 32 GB WRX90 kit specifications](https://www.gskill.com/_upload/files/F5-6400R3239G32GE8-G5N.pdf)

For a continuously running homelab host, prioritize an ASRock-QVL matched kit
and error-free operation over the highest overclocked memory profile.

## Combined upgrade

The upgrades complement each other:

- The 9975WX supplies enough cores for 16 CI jobs without consuming every
  logical CPU.
- 256 GB supports the corresponding 96 GB job-container memory budget while
  retaining ample space for AI services, database sidecars, and page cache.
- Eight populated memory channels better feed the doubled physical core count.
- The unchanged 350 W CPU TDP limits the platform changes needed for the CPU
  swap, although the full system power and cooling configuration should still
  be checked under simultaneous CPU and three-GPU load.

This is the upgrade to choose if `max` is intended to act as both a dense CI
worker and an always-on multi-GPU inference server. If the new 14-slot Linux
runner pool removes normal queueing, the combined hardware purchase is not yet
necessary.

## Post-upgrade verification

1. Drain or pause the max runner and stop active inference workloads.
2. Record BIOS settings and confirm 9975WX support with the installed BIOS.
3. Install either the CPU, one matched eight-DIMM kit, or both.
4. Boot at conservative memory settings before enabling any EXPO profile.
5. Confirm 64 logical CPUs for a 9975WX and all eight populated memory channels.
6. Run an extended memory test and inspect EDAC/MCE logs for corrected errors.
7. Stress CPU and memory while monitoring CPU, VRM, and DIMM temperatures.
8. Benchmark representative Kizuna pipelines and both CPU- and GPU-backed
   inference before raising runner concurrency.
9. Re-run the `development_linux` playbook after adjusting its runner limits.
