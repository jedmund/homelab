# max hardware, CI capacity, and local inference

Report date: October 11, 2026. Host observations below are dated explicitly;
the latest snapshot is 23:11 PDT. This consolidates the hardware discussion,
failure investigation, upgrade options, and Local Inference Lab model research.
It is a decision record, not a deployment procedure.

The immediate priority is to establish stability with the replacement HX1000i
and resolve the CPU_FAN1 telemetry problem. For expansion, eight populated
memory channels and a 9985WX address different constraints: memory capacity and
bandwidth versus parallel CPU work. A fourth 96 GB GPU enables specific
four-GPU inference recipes. None of these purchases is an established fix for
the unexplained shutdowns.

For the intended combination of more simultaneous CI jobs and local inference,
512 GB across eight DIMMs is the preferred long-term capacity if its price is
acceptable. A 256 GB eight-DIMM configuration remains a reasonable intermediate
choice. The current CI incidents do not, by themselves, demonstrate a need for
512 GB. The model choices and actual working-set measurements should determine
that purchase. The [October 15 update](#october-15-update-memory-sizing-for-eight-gpus-and-photon)
revises this: with eight GPUs waiting for the electrical upgrade, buy 512 GB
once. The [October 24 update](#october-24-update-512-gb-installed-and-board-replaced)
records the installed memory and the replacement motherboard.

## Hardware and running services

| Component | Recorded configuration |
| --- | --- |
| Motherboard | ASRock WRX90 WS EVO |
| CPU | AMD Ryzen Threadripper PRO 9955WX, 16 cores / 32 threads |
| RAM | 128 GB, four 32 GB ECC RDIMMs; four of eight memory channels populated |
| Memory identification | G.Skill `F5-6400R3239G32GQ`, running at 5600 MT/s in the September inspection |
| GPU 0 | RTX PRO 6000 Blackwell Max-Q Workstation Edition, 96 GB, PCI `21:00.0` |
| GPU 1 | RTX PRO 6000 Blackwell Max-Q Workstation Edition, 96 GB, PCI `D1:00.0` |
| GPU 2 | RTX PRO 6000 Blackwell Workstation Edition, 96 GB, PCI `F1:00.0` |
| GPU limits | All three report 300 W; GPU 2 has a 600 W factory default |
| Power | Replacement HX1000i outside the case; HX1500i inside the case |
| Kernel | `7.0.0-34-generic`, temporarily selected as the default after the comparison test |

The repository-managed `gpu-power-limits.service` applies the Workstation
card's 300 W limit at boot and deployment checks the reported value. It uses
exact model names so the Max-Q cards are not confused with the higher-power
Workstation model. The retired `nvidia-undervolt.service` was removed. The
limit reduces sustained GPU demand; it does not guarantee that every brief
transient is limited to 300 W. See [GPU host tools](../roles/gpu_tools/README.md).

At 23:11 on October 11, max had been up for one day and 13 minutes, following
the October 10 boot at approximately 22:57. The host reported 122 GiB usable
RAM, with about 110 GiB available at that quiet snapshot. This is useful
evidence of recovery, but previous failures have taken days to appear.

The running allocation differs from the original inference split:

| Service | State in the October 11 inspection | GPU allocation |
| --- | --- | --- |
| llama-swap | Running | Max-Q pair, GPUs 0 and 1 |
| TEI embeddings and Whisper | Running | Workstation card, GPU 2 |
| Kokoro | Running with the CPU image | CPU |
| DeepSeek V4 Flash 0731 vLLM container | Stopped | Configured for GPUs 0 and 1 |
| GitLab Runner | Running | CPU jobs |

llama-swap was moved to the Max-Q pair to preserve inference while the
Workstation card was removed. Reinstalling the card did not automatically
restore the previous split. The repository's intended split places vLLM on
the Max-Q pair and llama-swap on GPU 2. Restoring that arrangement is a separate
service change: starting DeepSeek while llama-swap still occupies the same
pair risks contention or allocation failure. See the
[AI runbook](../roles/ai/README.md) and [vLLM runbook](../roles/vllm/README.md).

## Power wiring and the failure investigation

The user confirmed this wiring:

| Supply | Connected equipment |
| --- | --- |
| HX1000i | Motherboard 24-pin power and the Workstation GPU |
| HX1500i | CPU EPS power, both Max-Q GPUs, motherboard auxiliary power, and the NZXT internal USB hub used for PSU telemetry |
| Synchronization | ASRock's supplied multi-PSU connector |
| AC input | Separate circuits; the actual outlet voltages and protective-earth condition have not been independently measured |

The external HX1000i rests on concrete. Its cables have slack and loops at the
connectors. The NZXT hub was installed after failures had already started.
These observations reduce the case for cable tension or the hub as the
original trigger; they do not identify the failing component.

The recurring failure is more specific than an ordinary application crash:
network access stops, the BMC reports the chassis off, fans can remain running,
the board shows `00`, and an AC cycle has been needed to recover. The recorded
events did not leave a useful kernel panic, netconsole trace, or corresponding
BMC hardware-fault entry. Code `00` and the BMC power reading do not identify
which rail, component, or software path initiated the state.

The [original incident record](max-power-events-2026-10.md) documents the early
events and instrumentation. Later tests change several of its interpretations:

| Observation or test | What it establishes | What remains unresolved |
| --- | --- | --- |
| Workstation fan physically obstructed by the sag bracket | A real cooling defect existed; loosening the bracket restored rotation | It does not establish that heat caused every outage; failures also occurred with low recorded temperatures |
| Ten-minute GPU 2 burn at 300 W alongside heavy CI | That run completed without computation errors; GPU temperature settled near 65°C | A short steady load does not test every idle transition, connector fault, or intermittent failure |
| Kernel `7.0.0-34` ran longer than two short runs on `7.0.0-38`, then failed too | The older kernel was not a complete workaround | A shared driver, firmware, PCIe power-management path, or kernel interaction remains possible |
| Another failure occurred with the Workstation card removed | That card is not required for the failure to occur | Removing it also changed load and service placement, so this does not clear every GPU or PCIe interaction |
| PSU readings looked normal before failures | No sustained abnormality was captured at the sampling times | Fifteen-second telemetry cannot exclude brief rail, Power Good, PS_ON, or connection faults |
| HX1000i replaced and Workstation card reinstalled together | A new operating configuration is under observation | Two variables changed together; stable uptime would support this configuration without proving which change mattered |

The earlier statements that the PSUs were conclusively healthy, that failure
on the older kernel proved hardware, or that a cold boot ruled out all thermal
issues were too strong. The available evidence supports hypotheses, not a
confirmed root cause.

### Leading hypotheses

The following is a working investigation order, not a statistical ranking:

1. **Original HX1000i or its motherboard power path.** Replacement directly
   tests part of the path supplying motherboard power. Cable reuse and the
   exact replacement generation matter when interpreting the result.
2. **Motherboard power sequencing, regulation, or a latched platform fault.**
   The unusual partially powered state makes this worth investigating, but
   no captured record identifies a board defect or an AMD sync-flood event.
3. **The remaining supply, EPS/auxiliary connections, or PSU synchronization.**
   The HX1500i and shared power-control arrangement remain common to the
   configurations that failed. Spinning fans cannot clear them.
4. **PCIe or GPU-driver power transitions.** Idle and load transitions, the
   NVIDIA runtime power settings, and the absence of useful host PCIe error
   reporting leave this open. It is not confined to the removed card.
5. **AC supply or grounding faults.** This deserves an actual wiring check,
   especially before the new installation. Separate circuits alone are not
   evidence of a fault.

CPU, memory, and localized thermal faults remain possible. The absence of
recorded ECC or machine-check errors is useful negative evidence, not a clean
bill of health for those components.

### Electrical questions and planned replacement equipment

The HX1000i telemetry reported approximately 230 V while the HX1500i reported
approximately 115 V. Treat those as reported values until measured. Corsair's
HXi documentation lists 100–240 V AC input for the covered model: a correctly
wired 240 V supply within the unit's rating is not inherently damaging.
Confirm the label and generation of the actual unit.
[Corsair HXi manual](https://assets.corsair.com/image/upload/v1701372411/documents/49_002658_AA_WW_HXi_Series_QSG_Web.pdf).

An intact external PSU does not require contact with the PC case to obtain
protective earth through its power cord. Being on concrete is not evidence
that it is shorting. Relevant checks are moisture, damaged insulation,
blocked ventilation, correct AC grounding, and the correct modular cables for
the exact PSU. Cable compatibility must be established from the manufacturer,
even when replacing a unit with another HX1000i.

The future plan is a 50 A circuit, two supplies described by the user as
Corsair 3000 W units, and an Eaton `9PX8KG2-L`. The exact PSU SKUs remain
unconfirmed and should be recorded before selecting cables or distribution.
The Eaton is an online double-conversion lithium-ion UPS, listed at 8 kVA / 8 kW,
with hardwired input, a recommended 50 A breaker, four L6-30R outlets plus
hardwired output, and a NETWORK-M3 card. Its nominal output supports
200/208/220/230/240 V; Eaton specifies different output power factors at 208 V
and 220–240 V. The electrician should design the installation around the exact
UPS and downstream equipment.
[Eaton specifications](https://www.eaton.com/us/en-us/skuPage.9PX8KG2-L.html).

That installation can improve power availability and observability. It will
not repair a defective connector, motherboard, or protective-earth connection.
Independent remote cycling of each PSU must be confirmed against the UPS's
controlled outputs and any managed PDU; the network card alone is not proof
of that capability. A smart plug remains intentionally deferred.

## Cooling alerts and BMC log capacity

The October 11 cooling investigation found a repeated **CPU_FAN1 zero-RPM
reading**, rather than a temperature threshold causing those alerts. In 485
two-minute samples, 66 recorded CPU_FAN1 at zero, about 13.6%. CPU temperature
in those samples was 35–37°C. CPU_FAN2/WP was around 3800–4000 RPM, and a live
check saw CPU_FAN1 return from zero to approximately 600 RPM within seconds.

The observed maximum temperatures over that review were CPU 82°C, GPU 0 81°C,
GPU 1 86°C, and GPU 2 29°C. These did not cross the configured temperature
alert thresholds in the reviewed samples. They do not establish temperature
under every workload, particularly on the recently reinstalled GPU.

Low idle fan speed, intermittent tachometer reporting, header configuration,
or a fan actually stopping are still distinguishable possibilities. Removing
the side panel does not establish which is happening or guarantee airflow
over every component. The cooler model and the devices attached to each fan
header still need to be recorded.

ASRock's supplied WRX90 guideline connects the CPU/radiator fan to CPU_FAN1 and
the AIO pump to CPU_FAN2/WP, with the latter at full speed by default. The board
manual rates those headers at 1 A / 12 W and 2 A / 24 W respectively. Check the
actual cooler's wiring and minimum controllable speed before changing fan
thresholds. The source manuals supplied for this investigation were
`WRX90 WS EVO.pdf` and `Guideline ASRock WRX90 WS EVO.pdf` in the user's Downloads
directory. The evenly blinking green light reported between PCIe slots is an
observation, not a diagnostic code established by this report.

SEL means **System Event Log**, the BMC's hardware-event log. It had filled with
3639 entries; 3622 concerned CPU_FAN1 assertion/deassertion transitions. After
archiving the entries, it was cleared with authorization on October 11 at
22:47:14 PDT. Verification showed zero percent used and no overflow. New
CPU_FAN1 entries resumed, so clearing the log creates temporary headroom but
does not fix the cause of the flood. Capture and recovery procedures belong
in the [crash-capture runbook](../roles/crash_capture/README.md).

## CI demand and the CPU upgrade

The latest CI investigation found two distinct constraints:

- The general runner pool was limited to six jobs even when the separate
  large-job pool was idle. The general limit was raised to eight while global
  concurrency remains eight and the large-job limit remains two. Valid mixes
  include eight general jobs, seven general plus one large job, and six
  general plus two large jobs. Both max runners were verified online after
  the change, and eight general jobs were observed running.
- Album Sort's Storybook smoke job launched 16 workers inside a container
  limited to three CPUs and 6 GiB. It reached its memory limit and incurred
  CPU throttling while the host still had substantial available RAM. An
  explicit two-worker CI setting passed its validation pipeline, including
  83 smoke tests in 40.1 seconds. That application change is tracked in
  [Album Sort MR 856](https://git.atelier.house/jedmund/album-sort/-/merge_requests/856).

General jobs have three-CPU and 6 GiB limits; large jobs have 12-CPU and 24 GiB
limits. At the largest admitted mixed workload, the limits sum to 42 CPUs and
84 GiB. CPU quotas are ceilings, not dedicated physical cores. More host RAM
does not increase a container's 6 GiB limit, and a new CPU does not correct an
application's excessive worker count. See the
[runner runbook](../roles/development_linux/README.md).

The [September CI report](ci-performance-2026-09-22.md) also identified storage
and scratch-I/O problems; its tmpfs test reduced one Vitest run from 237 to
66 seconds. That historical result explains why buying cores alone was not
the first intervention then. The current desire to run more simultaneous
pipelines changes the capacity question.

| CPU characteristic | 9955WX installed | 9985WX considered |
| --- | ---: | ---: |
| Cores / threads | 16 / 32 | 64 / 128 |
| Base clock | 4.5 GHz | 3.2 GHz |
| Maximum boost | Up to 5.4 GHz | Up to 5.4 GHz |
| L3 cache | 64 MB | 256 MB |
| Default TDP | 350 W | 350 W |
| Memory channels | 8 | 8 |

These are AMD specifications, not measured pipeline gains.
[9955WX](https://www.amd.com/en/products/processors/workstations/ryzen-threadripper/9000-wx-series/amd-ryzen-threadripper-pro-9955wx.html),
[9985WX](https://www.amd.com/en/products/processors/workstations/ryzen-threadripper/9000-wx-series/amd-ryzen-threadripper-pro-9985wx.html).

The 9985WX is a sensible throughput upgrade if CPU contention and queueing
remain high after the runner and worker fixes, particularly because the user
is deliberately holding back parallel work. Four times the cores is not a
promise of four-times-faster pipelines. Sequential steps, storage, network,
job dependencies, memory bandwidth, and unchanged container limits constrain
the result. Its strongest expected benefit is more jobs making progress at
once and shorter queues. Measure queue delay separately from execution time,
then retune concurrency and job limits after the upgrade.

## Memory: channels, capacity, speed, and purchase options

| Configuration | Active channels | Purpose and tradeoff |
| --- | ---: | --- |
| Current 128 GB, 4 × 32 GB | 4 | Existing capacity; half the CPU's channels populated |
| 256 GB, 8 × 32 GB | 8 | Doubles capacity and channel count; strong value for expanded CI |
| 256 GB, 4 × 64 GB | 4 | More capacity, but leaves the present channel-count limitation |
| 512 GB, 8 × 64 GB | 8 | Same channel count as 8 × 32 GB, with more room for CI, model tables, and caches |

At the same transfer rate, 512 GB does not have twice the theoretical bandwidth
of an eight-DIMM 256 GB setup. It buys capacity. Populating the other four
channels is the bandwidth change. These calculated ceilings illustrate the
difference; applications will achieve less:

| Transfer rate | Four-channel payload ceiling | Eight-channel payload ceiling |
| --- | ---: | ---: |
| 4800 MT/s | 153.6 GB/s | 307.2 GB/s |
| 5600 MT/s | 179.2 GB/s | 358.4 GB/s |
| 6000 MT/s | 192.0 GB/s | 384.0 GB/s |
| 6400 MT/s | 204.8 GB/s | 409.6 GB/s |

Calculation: channels × transfers/second × eight payload bytes. DDR5 speed
labels here are MT/s, even where shops call them MHz. Moving from 5600 to 6400
raises that ceiling by 14.3%; 6000 to 6400 adds 6.7%. Neither percentage is a
predicted CI or token-generation improvement. Timings, ranks, achieved clock,
and workload also matter.

The buying preference is eight supported ECC **RDIMMs**, with capacity and
stable operation ahead of an aggressive EXPO setting. Ordinary desktop ECC
UDIMMs are not interchangeable with this requirement. Check the exact board,
CPU, BIOS, module density, and eight-DIMM qualification. Do not assume that a
generic WRX90 compatibility statement qualifies every 512 GB speed variant.

### 512 GB candidates to watch

| Candidate | Published specification | Purchase condition |
| --- | --- | --- |
| Eight Kingston Server Premier `KSM64R52BD4-64MH` modules | Each is 64 GB, 2Rx4 ECC RDIMM, DDR5-6400 CL52, 1.1 V | This is a module SKU, not a boxed matched eight-DIMM kit; obtain a supported, consistent set and confirm board qualification |
| V-Color WRX90 512 GB, 8 × 64 GB OC RDIMM family | Listed variants include 4800, 5600, 6000, and 6400; the 5600 entry includes `TRA564G56D436O` | Confirm the exact eight-module order code and ASRock support; the page's 512 GB compatibility subsection does not explicitly list this ASRock board |
| G.Skill `F5-6400R3848F64GE8-T5N` | 512 GB, 8 × 64 GB, EXPO up to 6400 CL38-48-48-102 at 1.35 V; default SPD 5600 at 1.1 V | Requires BIOS support for 64 GB modules; maximum EXPO speed depends on the platform |

Specifications:
[Kingston datasheet](https://www.kingston.com/datasheets/KSM64R52BD4-64MH.pdf),
[V-Color product family](https://v-color.net/products/ddr5-ocrdimm-amd-wrx90-workstationmemory),
[G.Skill kit specification](https://www.gskill.com/specification/400/452/1755678629/F5-6400R3848F64GE8-T5N-Specification).
These are candidates for compatibility confirmation, not certified kits for
max or statements of current stock. Prices and availability need checking at
purchase time.

On V-Color versus Kingston, no comparative failure-rate evidence was
established in this discussion. Forum recommendations and vendor reviews
cannot establish one. Kingston's JEDEC Server Premier option is attractive
for conservative operation; V-Color offers explicit workstation overclocking
variants. Choose by exact qualification, achievable settings, seller support,
and replacement policy rather than a blanket brand verdict. Establish a
stable default-speed baseline before experimenting with faster profiles.

## Local Inference Lab: model choices and hardware implications

The upstream material reviewed is
[local-inference-lab/rtx6kpro](https://github.com/local-inference-lab/rtx6kpro),
at commit `d24d7ce6b4eee06552d2d4b096a6418a4666c51e`, reviewed October 11.
The links below pin that snapshot. These are community serving recipes and
measurements, not a guarantee of performance or model quality on max.

TP is tensor parallelism: TP2 divides a model across two GPUs, and TP4 across
four. DCP is decode context parallelism. MTP, DSpark, and DFlash are different
speculative decoding methods; their draft depths and model compatibility
cannot be exchanged indiscriminately. VRAM totals below are nominal hardware
capacity, not memory remaining after weights, runtime buffers, and KV cache.

| Model / recipe | Documented GPU layout | Why it matters for max |
| --- | --- | --- |
| [DeepSeek V4 Flash 0731, text](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/deepseek-v4-flash.md) | TP2, 192 GB; DSpark K5 | Existing locally validated vLLM profile on the Max-Q pair; currently stopped |
| [DeepSeek V4 Flash Vision](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/deepseek-v4-flash-vision.md) | TP2, 192 GB; DSpark K3 | A separate checkpoint and vision-serving recipe, not a switch added to the text checkpoint |
| [GLM-5.3 Flash NVFP4 Spark](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/glm-5.3-flash-spark-tp2.md) | TP2/DCP2, 192 GB; MTP3 | Downloaded and tested on max as an alternative to DeepSeek; Spark names the tuned checkpoint, not a requirement for a DGX Spark machine |
| [Qwen3.8 Flash Next](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/qwen38-flash-next.md) | TP1 or TP2; NVFP4 and MTP3 recipes | A candidate for a single 96 GB card; its CPU-side PLE tables also consume host RAM or use the documented disk path |
| [GLM-5.3 Flash, full checkpoint](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/glm-5.3-flash.md) | TP4, 384 GB; MTP3 or DFlash2 K7 | A reason to consider a fourth card; not the Spark checkpoint with its TP setting changed |
| [DeepSeek V4.1 Flash](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/deepseek-v4.1-flash.md) | TP4, 384 GB; adaptive DSpark K7 | Text and vision candidate after a fourth card; Engram tables have separate host-memory/storage requirements |

Qwen3.8 Flash Next and the dense Qwen3.8 27B family are different models. A
27B GGUF already fitting llama-swap does not validate the Flash Next serving
recipe. Qwen's documented CPU PLE path has used about 26.82 GiB for the mapped
table, before other host overhead. DeepSeek V4.1 offers RAM and disk Engram
paths, with disk as the documented default. Its historical TP4 accounting
lists **188.83 GiB for RAM-resident Engram tables alone**, before loader,
server, and OS memory. This is a concrete reason to consider 512 GB: those
tables plus the current CI pools' maximum 84 GiB of memory limits already
exceed 256 GiB. The limits are not reserved usage, but concurrent peaks need
room. The SSD path is an alternative with different performance; it is not
the path used for the upstream speed figures below.

### Three separate uses of memory

| Memory consumer | Resource used | Effect of a RAM upgrade |
| --- | --- | --- |
| GPU weights, active KV cache, and execution buffers | GPU VRAM | Host RAM does not automatically enlarge this GPU budget |
| Model-specific tables such as PLE or Engram | Host RAM or the model's supported storage path | More RAM and channels can help the selected path; the benefit is model-specific |
| Optional reusable prefix cache through LMCache | Configured RAM and/or SSD tiers | Can avoid repeated prompt processing; it does not make every new prompt or decode step faster |

The upstream [unified runtime documentation](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/docs/unified-vllm-docker.md)
describes the Karmic Kraken image and profile-specific settings. max's
September-tested image is pinned by digest, with external prefix caching
disabled. A moving upstream image tag is not the same tested artifact.
Retain the checkpoint, image, API name, parser settings, cache layout, and
rollback configuration when comparing candidates.

Four cards would provide 384 GB nominal VRAM, but a TP4 model generally uses
all four together. That competes with separate llama-swap, embedding, speech,
and other GPU services. More total VRAM does not guarantee that arbitrary
TP3 layouts work. PCIe topology, peer access, physical spacing, auxiliary
power, and cooling need validation after changing the card population.

### Measurements obtained on max

The following are historical September 21 results, not a fresh October
benchmark. C1, C2, and C4 denote concurrent requests; the rates are aggregate
decode throughput, not per-request throughput at those concurrency levels.

| Profile on the Max-Q pair | C1 tokens/s | C2 tokens/s | C4 tokens/s | Evidence |
| --- | ---: | ---: | ---: | --- |
| DeepSeek V4 Flash, Karmic K5, 4096-token prefill budget | 194.1 | 275.3 | 401.9 | Three-pass medians |
| GLM-5.3 Flash Spark, MTP3 | 175.6 | 262.4 | 372.6 | One pass |

DeepSeek's smaller prefill batch recovered shared KV capacity to 338,122
tokens, versus 154,127 in the older r15 baseline. This accommodated four
32K prompts or two 120K prompts with the benchmark's output allowance, not
four independent full-size 120K conversations. Short decode speed did not
show a general improvement over r15. Read the complete
[DeepSeek runtime comparison](inference-runtime-upgrade-2026-09-21.md) for
host-state differences, long-context results, and startup behavior.

GLM Spark's downloaded snapshot occupied about 175 GiB on disk. It completed
the selected tests through four concurrent 120K prompts; the runtime reported
953,418 shared KV tokens and a fitted per-request maximum of 950,272. Those
reported capacities are not validation of useful answers near that maximum.
The first startup took 521 seconds and a cached restart 280 seconds.
[GLM setup and validation](inference-glm-setup-2026-09-21.md).

Both profiles passed basic chat/code review and strict JSON/tool assertions,
but operations-handoff samples invented completed checks or healthy system
states. GLM also exceeded the requested answer length in all six samples.
The limited local comparison did not establish a GLM speed or quality win,
so DeepSeek remained the configured default and GLM an optional alternative.
Successful serving and higher token rates do not establish more dependable
agent behavior.

### Upstream performance reference

Local Inference Lab's Karmic comparison used Max-Q cards at **325 W with a
reported +6000 VRAM overclock**, unlike max's 300 W settings. It used five
warm 30-second windows. The following zero-context decode results are for
capacity planning only, not forecasts for max:

| Recipe | GPUs | Single request, tokens/s | Concurrent aggregate, tokens/s |
| --- | ---: | ---: | ---: |
| DeepSeek V4 text, DSpark K5 | 2 | 212.5 | 667.5 at C8 |
| DeepSeek V4 Vision, DSpark K3 | 2 | 193.9 | 401.4 at C4 |
| Qwen3.8 Flash Next, MTP3 | 1 | 173.2 | 698.4 at C8 |
| DeepSeek V4.1, adaptive DSpark K7 | 4 | 249.1 | 805.5 at C8 |
| GLM-5.3 Flash, MTP3 | 4 | 281.3 | 897.6 at C8 |
| GLM-5.3 Flash, DFlash2 K7 | 4 | 229.0 | 702.6 at C8 |

[Upstream benchmark and methodology](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/benchmarks/karmic-kraken-serving.md).
The DeepSeek V4.1 measurement uses RAM-resident Engram tables. Models,
tokenizers, GPU counts, and speculation differ. The numbers neither rank
answer quality nor imply that a larger speculative draft is faster.

### Larger and historical model families

The Lab also documents models outside the proposed four-card configuration:

- [Kimi K2.7 Code v3](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/kimi-k27-code_v3.md): an eight-GPU TP8/DCP4 recipe.
- [MiMo V2.5 Pro FP4 with DFlash v3](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/xiaomi-mimo-v2.5-pro-fp4-dflash_v3.md): an eight-GPU TP8 recipe.
- [Kimi K3](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/kimi-k3/README.md): an official TP16/DCP16 path and a separate quantized nine-GPU path.
- [DeepSeek V4 Pro Lucifer](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/models/deepseek-v4-pro-tp16-lucifer.md): a sixteen-GPU recipe.

These are not unlocked by buying 512 GB of system RAM or one more GPU. The
wiki also retains GLM-5.2/5.1, Kimi K2.5/K2.6, GLM-4.7, MiniMax-M2.5, and
Qwen3.5 recipes and archives. Their presence is not a recommendation to replace
the current model. Use the [model catalogue](../roles/ai/MODELS.md) for the
homelab's own served models and the
[upstream model index](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/README.md)
for the wider set.

### Upstream stability reports that affect the investigation

The Lab's [multi-PSU grounding case](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/troubleshooting/gpu-bus-drops-multi-psu-grounding.md)
involved a 9955WX, an ASUS WRX90 board, sixteen GPUs, four PSUs, and a PCIe
switch arrangement. Missing protective earth was found, and correcting it
was followed by more than 48 hours without the previous GPU bus drops. It
supports checking actual grounding. It does not establish that max has that
fault or that different correctly grounded circuits are inherently unsuitable.
Any corrective AC grounding work belongs with the electrician.

The [common-issues page](https://github.com/local-inference-lab/rtx6kpro/blob/d24d7ce6b4eee06552d2d4b096a6418a4666c51e/troubleshooting/common-issues.md)
also describes Surprise Link Down associated with PCIe runtime power
transitions and suggests `pcie_aspm=off pcie_port_pm=off`. This remains a
candidate controlled test for max, not a diagnosed cause or an applied fix.
Do not combine it with unrelated IOMMU, driver, BIOS, and hardware changes in
one experiment. The earlier NVIDIA runtime-power-management lead likewise
has not been tied to a captured failure on this host.

The inspected VBIOS versions are `98.02.6A.00.03` on both Max-Q cards and
`98.02.81.00.07` on the Workstation card. No applicable firmware repair was
verified in this investigation. A newer Dell Server Edition image discussed
earlier was for a different board and is not an upgrade for these cards.
Establish any firmware candidate through the exact card vendor and board
identity before considering it.

## October 15 update: memory sizing for eight GPUs and Photon

The user reported eight GPUs on hand, waiting for the electrical upgrade. That
changes the memory decision above. The earlier text weighed a fourth card;
eight cards make the multi-card layouts the default rather than the exception.

A 15:20 PDT snapshot showed the same four 32 GB `F5-6400R3239G32GQ` RDIMMs in
four of eight slots, 122 GiB visible to the OS, and about 89 GiB available.
The 8 GiB swap area was almost entirely used (96 MiB free), so peaks have
already pushed memory out at some point. llama-swap was the largest
container at 33 GiB. The root volume had 470 GB free (74% used). dmidecode
reports eight slots and a 4 TB maximum.

**Recommendation: buy 512 GB as 8 × 64 GB once, rather than 256 GB first.**

- **Host memory demand scales with the GPUs being served.** vLLM stages
  weights through host memory on load and keeps runtime buffers there.
  Model-specific tables add to that: Qwen3.8 Flash Next's PLE table is about
  26.82 GiB, and DeepSeek V4.1's RAM-resident Engram tables are 188.83 GiB
  for a TP4 deployment. Eight cards make it likely that more than one large
  model, or one model across all eight cards, runs at once. If the eight
  cards are 96 GB each, they hold 768 GB of VRAM; 256 GB of host memory
  would be a constant constraint.
- **The 256 GB case was already marginal for one large model.** The Engram
  tables plus the CI pools' 84 GiB of memory limits exceed 256 GiB before
  loader, server, and OS memory.
- **Upgrading twice costs more.** 512 GB replaces every module, so buying
  256 GB now means buying a second full set of memory later. Filling all
  eight channels is the bandwidth change either way; 512 GB adds capacity at
  the same bandwidth.
- **512 GB is not the ceiling, but the next step is costly.** With eight
  slots, one module per channel, 8 × 64 GB fills the board. The only larger
  configuration is 8 × 128 GB for 1 TB, which replaces the set again. If the
  eight-GPU build is likely to need 1 TB, price that before ordering 512 GB.

The qualification requirement above still applies: confirm the exact 64 GB
kit against this board and BIOS. A generic WRX90 compatibility statement
does not cover every 512 GB speed variant.

**Photon is not a reason to buy more memory.** Kizuna's chat maps need a
self-hosted geocoder. The worldwide Photon index is a 63.2 GB download and
about 95 GB on disk, and Photon recommends at least 64 GB of RAM for it. That
fits max's disk today, but not comfortably beside CI peaks and llama-swap
on 128 GB. The user chose a US and Japan database instead, imported from
the worldwide JSON dump with `-country-codes us,jp`. The US-only database
alone is a 10.5 GB download, so the combined database is small enough for
nuc-mini, with max as the fallback host if lookups there are slow. After a
512 GB upgrade, a worldwide Photon index on max would fit easily.

## October 24 update: 512 GB installed and board replaced

The 512 GB kit is installed, and the motherboard was replaced at the same time.
The ASRock board's A0 memory slot was defective, so the host now runs on an
ASUS Pro WS WRX90E-SAGE SE. Read from max at 18:01 PDT, eight minutes after
boot:

| Component | Configuration |
| --- | --- |
| Motherboard | ASUS Pro WS WRX90E-SAGE SE, BIOS 1317; BMC firmware 2.01 |
| CPU | AMD Ryzen Threadripper PRO 9985WX, 64 cores / 128 threads |
| RAM | 512 GB, eight 64 GB Samsung 2Rx4 ECC RDIMMs, one per channel; 498 GiB visible to the OS |
| Memory identification | Six `M321R8GA0EB2-CJRQK` and two `M321R8GA0EB2-CJRTK`; rated 7200 MT/s, configured at 6400 MT/s |
| GPU PCI addresses | `21:00.0`, `C1:00.0`, `F1:00.0`; index order unchanged, GPU 1 moved from `D1:00.0` |
| Storage | 2 TB Samsung 990 PRO for the OS and `/opt/docker` (440 GB free); 4 TB Samsung 990 PRO, ext4 at `/mnt/storage`, formatted October 23 and still empty |
| Swap and `/dev/shm` | 8 GiB swap file, unused; `/dev/shm` 250 GiB |
| kdump | Ready, with 4 GiB reserved by the `128G-:4096M` crashkernel band |

The two part-number suffixes indicate that the modules do not all come from one
production lot. The board trained all eight at 6400 MT/s.

**ECC history.** rasdaemon recorded 2,101 corrected memory errors on the
ASRock board between October 13 16:44 and October 23 22:54. Most were on
memory channel 3, with smaller counts on channels 9 and 0. There were no
uncorrected errors. The October 23 evening boots ran with 32 GB and then
64 GB, which is consistent with isolating DIMMs or slots. The ASUS board
has booted eight times since October 24 09:15 with 512 GB each time. No
corrected errors have been recorded on it, and the EDAC counters were zero
at 18:01. The [power event record](max-power-events-2026-10.md) reported no
ECC errors through October 7. These errors began afterwards.

**Repository changes for the new board.** The crash-capture cooling limits
matched ASRock BMC sensor names (`TEMP_CPU`, `TEMP_DDR5_*`, `CPU_FAN1`). None
of these exist on the ASUS BMC, so only BMC critical states were being
checked. The limits now use the ASUS names, and the SEL-flapping sensor
changed from `CHA_FAN1/WP` to `CHA_FAN4`. See the
[crash capture runbook](../roles/crash_capture/README.md#bmc-event-log).
Nothing in vLLM, llama-swap, or SGLang is sized by host RAM. `shm_size`,
`memlock`, and the VRAM prompt cache are unaffected.

**Not verified.** This record has no evidence of a memory test or burn-in
of the new kit. One week of uptime under CI and inference load without
corrected errors would be the first stability checkpoint. The sustained CPU
and memory stress in step 5 below still applies.

## Recommended sequence and decision points

1. **Continue the replacement-PSU observation with the current configuration.**
   Record idle periods, CI bursts, inference use, boot IDs, and any recurrence.
   Forty-eight to seventy-two hours is an early checkpoint, not a declaration
   of repair; exceeding the previous multi-day failure intervals is stronger
   evidence. Do not introduce overclocking during this period.
2. **Resolve CPU_FAN1 and protect event-log capacity.** Identify the cooler and
   header wiring, distinguish a real fan stop from a tachometer dropout, and
   then correct the fan control or monitoring configuration. Preserve SEL
   evidence before clearing; watch for another fill rather than treating the
   clear as a lasting repair.
3. **If the abnormal power state returns, preserve the evidence before more
   changes.** Compare the boot report, final model-labelled PSU samples,
   netconsole, SEL, load, and physical state. The replacement would weaken the
   old-PSU-only explanation and raise the common motherboard, EPS/auxiliary,
   synchronization, and PCIe paths. Choose one next isolation test from that
   evidence rather than declaring a component cleared by one successful run.
4. **Keep the CI fixes and measure the remaining demand.** Track queue time,
   execution time, cgroup memory peaks, CPU throttling, and I/O pressure under
   the additional parallel work the user actually wants. Hardware sizing
   should include that demand, not only the current deliberately limited load.
5. **Stage CPU and RAM upgrades separately.** Prefer eight channels. Buy
   512 GB as 8 × 64 GB; the October 15 update explains why eight GPUs rule
   out stopping at 256 GB. Select the 9985WX when CPU throughput is the next
   constraint; validate memory stability and rerun representative pipelines
   before increasing concurrency aggressively.
6. **Choose an inference layout before a fourth GPU purchase.** Two-GPU
   DeepSeek or GLM Spark plus a separate llama-swap card is already within
   installed capacity. Qwen Flash Next is a candidate single-card experiment.
   Full GLM-5.3 Flash or DeepSeek V4.1 motivates four cards, but requires an
   explicit plan for the services displaced by a TP4 model.
7. **Validate models on useful tasks before promoting them.** Preserve a
   working rollback, then test readiness, restarts, JSON/tool behavior,
   long-context concurrency, factual task performance, and contention with
   CI. Compare power-capped stock settings first. Follow the
   [inference upgrade plan](inference-upgrade-plan.md) for the existing order
   of runtime, cache, and model experiments.

This report changes documentation only. It does not end the stability test,
alter hardware or firmware, switch models, change runner limits, or deploy
any of the proposed upgrades.
